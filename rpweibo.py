import curl
import pycurl
from io import BytesIO
import urllib.parse
import base64
import rsa
import json
import itertools
import time


__version__ = "0.02.2"

g_retry = -1


def set_retry(times):
    global g_retry
    g_retry = int(times)


class _Curl(curl.Curl):
    """Returns a pycurl.Curl() with serveral settings."""

    def __init__(self, base_url="", fakeheaders=()):
        super().__init__(base_url, fakeheaders)
        self.set_option(pycurl.SSL_VERIFYPEER, True)
        self.set_option(pycurl.ENCODING, "")  # accept all encodings

        # workaround buggy pycurl versions before Dec 2013
        self.payload = None
        self.payload_io = BytesIO()
        self.set_option(pycurl.WRITEFUNCTION, self.payload_io.write)

        def header_callback(x):
            if isinstance(x, str):
                # workaround buggy pycurl versions
                self.hdr += x
            else:
                self.hdr += x.decode("ascii")
        self.set_option(pycurl.HEADERFUNCTION, header_callback)

        # use the only one secure cipher that Sina supports
        if "OpenSSL" in pycurl.version_info()[5]:
            self.set_option(pycurl.SSL_CIPHER_LIST, "ECDHE-RSA-AES256-SHA")
        else:
            # Assume GnuTLS. what? You've built libcurl with NSS? Hum...
            self.set_option(pycurl.SSL_CIPHER_LIST, "PFS")

    def __request(self, relative_url=None):
        super().__request(relative_url)
        self.payload = self.payload_io.getvalue().decode("UTF-8")
        return self.payload

    def get(self, url="", params=None):
        "Ship a GET request for a specified URL, capture the response."
        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)
        self.set_option(pycurl.HTTPGET, 1)
        return self.__request(url)

    def post_binary(self, cgi, params):
        "Ship a POST request, treats bytes in params as the binary data."
        postdata = []
        for param, value in params.items():
            if isinstance(value, bytes):
                postdata.append((param, (pycurl.FORM_BUFFER, param, pycurl.FORM_BUFFERPTR, value)))
            else:
                postdata.append((param, (pycurl.FORM_CONTENTS, urllib.parse.quote(value))))
        self.set_option(pycurl.HTTPPOST, postdata)
        return self.__request(cgi)


class WeiboError(Exception):
    pass


class RequestError(WeiboError):
    pass


class NetworkError(RequestError):
    pass


class APIError(RequestError):

    def __init__(self, error_code, error_message):
        self.error_code = int(error_code)
        self.error_message = str(error_message).strip()

    def __str__(self):
        return "%d: %s" % (self.error_code, self.error_message)

    def __repr__(self):
        return self.__str__()


class RemoteError(APIError):
    pass


class CallerError(APIError):
    pass


class ResultCorrupted(RequestError):
    pass


class AuthorizeError(WeiboError):
    pass


class AuthorizeFailed(AuthorizeError):
    pass


class NotAuthorized(AuthorizeError):
    pass


class Application():

    def __init__(self, app_key, app_secret, redirect_uri):
        self.app_key = app_key
        self.app_secret = app_secret
        self.redirect_uri = redirect_uri


class getable_dict(dict):

    def __init__(self, dic):
        super().__init__(dic)

    def __getattr__(self, attr):
        return self[attr]


class Weibo():

    API = "https://api.weibo.com/2/%s.json"
    HTTP_GET = 1
    HTTP_POST = 2
    HTTP_UPLOAD = 3

    # if you find out more, add the error code to the tuple
    UNREASONABLE_ERRORS = (
        10003,  # Remote service error
        10011,  # RPC error
        21321,  # Applications over the unaudited use restrictions
    )

    PRIVILEGED_APIS = {
        "statuses/user_timeline": {"identifier_required": True},
        "users/show": {"identifier_required": True},
        "users/domain_show": {"identifier_required": False},
        "users/counts": {"identifier_required": True},
    }

    def __init__(self, application):
        self.application = application
        self._access_token = ""
        self._authorize_code = ""

    def auth(self, authenticator):
        access_token = authenticator.auth(self.application)
        if access_token:
            self._access_token = access_token
            try:
                self._authorize_code = authenticator.authorize_code
            except AttributeError:
                pass
        else:
            return False

    def __request(self, action, api, kwargs, privileged=True):
        if not self._access_token:
            raise NotAuthorized

        # hack for https://github.com/WeCase/WeCase/issues/119
        if (privileged and api in self.PRIVILEGED_APIS and self._authorize_code and
            (not self.PRIVILEGED_APIS[api]["identifier_required"] or
             (self.PRIVILEGED_APIS[api]["identifier_required"] and (("uid" in kwargs) or ("screen_name" in kwargs))))):
            if "uid" in kwargs and "screen_name" not in kwargs:
                screen_name = self.__request(self.HTTP_GET, "users/show", {"uid": kwargs["uid"]}, privileged=False).get("screen_name")
                kwargs["screen_name"] = screen_name
                del kwargs["uid"]
            kwargs["source"] = self.application.app_key
            kwargs["access_token"] = self._authorize_code
        else:
            kwargs["access_token"] = self._access_token

        request_url = self.API % api

        curl = _Curl()
        if action == self.HTTP_GET:
            result = curl.get(request_url, kwargs)
        elif action == self.HTTP_POST:
            result = curl.post(request_url, kwargs)
        elif action == self.HTTP_UPLOAD:
            image = kwargs.pop("pic")
            kwargs["pic"] = image.read()
            image.close()
            result = curl.post_binary(request_url, kwargs)

        status_code = curl.get_info(pycurl.RESPONSE_CODE)
        try:
            result_json = json.loads(result, object_hook=getable_dict)
            if not isinstance(result_json, dict):
                return result_json
            if "error_code" in result_json.keys():
                raise APIError(result_json["error_code"], result_json["error"])
            return getable_dict(result_json)
        except (TypeError, ValueError):
            if status_code != 200:
                raise APIError(status_code, "Unknown Error")
            raise ResultCorrupted

    def _request(self, action, api, kwargs):
        exception = None

        delay = 1
        for retry in itertools.count():
            if retry == g_retry:
                break

            if retry != 0:
                time.sleep(delay)

            if retry > 3:
                delay = 3
            elif retry > 5:
                delay = 5

            try:
                return self.__request(action, api, kwargs)
            except APIError as e:
                exception = e
                if e.error_code in self.UNREASONABLE_ERRORS or exception.error_code <= 10014:
                    pass
                else:
                    raise CallerError(exception.error_code, exception.error_message)
            except ResultCorrupted:
                pass
            except pycurl.error:
                pass

        if isinstance(exception, pycurl.error):
            raise NetworkError
        else:
            raise exception

    def get(self, api, **kwargs):
        return self._request(self.HTTP_GET, api, kwargs)

    def post(self, api, **kwargs):
        if "pic" in kwargs:
            return self._request(self.HTTP_UPLOAD, api, kwargs)
        else:
            return self._request(self.HTTP_POST, api, kwargs)

    def api(self, api):
        return WeiboAPI(self, api)


class WeiboAPI():

    def __init__(self, weibo, api):
        self._weibo = weibo
        self._api = api

    def get(self, **kwargs):
        return self._weibo.get(self._api, **kwargs)

    def post(self, **kwargs):
        return self._weibo.post(self._api, **kwargs)


class AccessTokenAuthenticator():

    def __init__(self, access_token):
        self._access_token = access_token

    def auth(self, application):
        return self._access_token


class UserPassAutheticator():

    PRELOGIN_PARAMETER = {
        'entry': 'openapi',
        'callback': 'sinaSSOController.preloginCallBack',
        'rsakt': 'mod',
        'client': 'ssologin.js(v1.4.15)',
        'su': '',
    }

    LOGIN_PARAMETER = {
        'entry': 'openapi',
        'gateway': '1',
        'from': '',
        'savestate': '0',
        'useticket': '1',
        'vsnf': '1',
        'vsnval': '',
        'door': '',
        'scope': '',  # scope of the application
        'su': '',
        'service': 'miniblog',
        'servertime': '',
        'nonce': '',
        'pwencode': 'rsa2',
        'rsakv': '',
        'sp': '',
        'encoding': 'UTF-8',
        'cdult': '2',
        'domain': 'weibo.com',
        'prelt': '1609',
        'returntype': 'TEXT',
    }

    OAUTH2_PARAMETER = {
        'response_type': 'code',
        'action': 'login',
        'isLoginSina': 0,
        'from': '',
        'regCallback': '',
        'state': '',
        'ticket': '',
        'withOfficalFlag': 0
    }

    PRELOGIN_URL = "https://login.sina.com.cn/sso/prelogin.php"
    LOGIN_URL = "https://login.sina.com.cn/sso/login.php?client=%s"
    AUTHORIZE_URL = "https://api.weibo.com/oauth2/authorize"
    ACCESS_TOKEN_URL = "https://api.weibo.com/oauth2/access_token"

    def __init__(self, username, password):
        self._username = username
        self._password = password
        self.authorize_code = ""

    def _request_authorize_code(self, application):
        # Encode the username to a URL-encoded string.
        # Then, calculate its base64, we need it later
        username_encoded = urllib.parse.quote(self._username)
        username_encoded = username_encoded.encode("UTF-8")  # convert to UTF-8-encoded byte string
        username_encoded = base64.b64encode(username_encoded)

        # First, we need to request prelogin.php for some necessary parameters.
        prelogin = self.PRELOGIN_PARAMETER
        prelogin['su'] = username_encoded

        curl = _Curl()
        try:
            prelogin_result = curl.get(self.PRELOGIN_URL, prelogin)
        except pycurl.error:
            raise NetworkError
        finally:
            curl.close()

        # The result is a piece of JavaScript code, in the format of
        # sinaSSOController.preloginCallBack({json here})
        prelogin_json = prelogin_result.replace("sinaSSOController.preloginCallBack(", "")[0:-1]
        prelogin_json = json.loads(prelogin_json)

        # Second, we request login.php to request for a authenticate ticket
        login = self.LOGIN_PARAMETER
        login['su'] = username_encoded
        login['servertime'] = prelogin_json['servertime']
        login['nonce'] = prelogin_json['nonce']
        login['rsakv'] = prelogin_json['rsakv']

        # One more thing, we need to encrypt the password with extra token
        # using RSA-1024 public key which the server has sent us.
        rsa_pubkey_bignum = int(prelogin_json['pubkey'], 16)  # the public key is a big number in Hex
        rsa_pubkey = rsa.PublicKey(rsa_pubkey_bignum, 65537)  # RFC requires e == 65537 for RSA algorithm

        plain_msg = "%s\t%s\n%s" % (prelogin_json['servertime'], prelogin_json['nonce'], self._password)
        plain_msg = plain_msg.encode('UTF-8')  # to byte string
        cipher_msg = rsa.encrypt(plain_msg, rsa_pubkey)
        cipher_msg = base64.b16encode(cipher_msg)  # to Hex

        login['sp'] = cipher_msg

        curl = _Curl()
        try:
            login_result = curl.post(self.LOGIN_URL % "ssologin.js(v1.4.15)", login)
        except pycurl.error:
            raise NetworkError
        finally:
            curl.close()

        # the result is a JSON string
        # if success, Sina will give us a ticket for this authorized session
        login_json = json.loads(login_result)
        if "ticket" not in login_json:
            raise AuthorizeFailed(str(login_json))

        oauth2 = self.OAUTH2_PARAMETER
        oauth2['ticket'] = login_json['ticket']  # it's what all we need
        oauth2['client_id'] = application.app_key
        oauth2['redirect_uri'] = application.redirect_uri

        curl = _Curl()
        curl.set_option(pycurl.FOLLOWLOCATION, False)  # don't follow redirect
        curl.set_option(pycurl.REFERER, self.AUTHORIZE_URL)  # required for auth
        try:
            # After post the OAuth2 information, if success,
            # Sina will return "302 Moved Temporarily", the target is "http://redirect_uri/?code=xxxxxx",
            # xxxxxx is the authorize code.
            curl.post(self.AUTHORIZE_URL, oauth2)
            redirect_url = curl.get_info(pycurl.REDIRECT_URL)
        except pycurl.error:
            raise NetworkError
        finally:
            curl.close()

        if not redirect_url:
            raise AuthorizeFailed("Invalid Application() or wrong username/password.")

        authorize_code = redirect_url.split("=")[1]
        self.authorize_code = authorize_code
        return authorize_code

    def _request_access_token(self, application, authorize_code):
        access_token_parameter = {
            'client_id': application.app_key,
            'client_secret': application.app_secret,
            'grant_type': 'authorization_code',
            'code': authorize_code,
            'redirect_uri': application.redirect_uri
        }

        curl = _Curl()
        try:
            result = curl.post(self.ACCESS_TOKEN_URL, access_token_parameter)
        except pycurl.error:
            raise NetworkError

        try:
            return json.loads(result)["access_token"]
        except KeyError:
            raise AuthorizeError

    def auth(self, application):
        authorize_code = self._request_authorize_code(application)
        return self._request_access_token(application, authorize_code)


class ManualAutheticator():

    WEIBO_DOMAIN = "api.weibo.com"
    AUTHORIZE_URL = "https://%s/oauth2/authorize" % WEIBO_DOMAIN
    ACCESS_TOKEN_URL = "https://%s/oauth2/access_token" % WEIBO_DOMAIN

    def __init__(self):
        pass

    def _request_authorize_code(self, application):
        print("Please open %s?client_id=%s&redirect_uri=%s in the web browser" % (self.AUTHORIZE_URL, application.app_key, application.redirect_uri))
        authorize_code = input("Authorize Code: ").strip()
        return authorize_code

    def _request_access_token(self, application, authorize_code):
        access_token_parameter = {
            'client_id': application.app_key,
            'client_secret': application.app_secret,
            'grant_type': 'authorization_code',
            'code': authorize_code,
            'redirect_uri': application.redirect_uri
        }

        curl = _Curl()
        try:
            result = curl.post(self.ACCESS_TOKEN_URL, access_token_parameter)
        except pycurl.error:
            raise NetworkError

        return json.loads(result)["access_token"]

    def auth(self, application):
        authorize_code = self._request_authorize_code(application)
        return self._request_access_token(application, authorize_code)
