import curl
import pycurl
import urllib.parse
import json
import itertools
import time


__version__ = "0.01"

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

    def __request(self, relative_url=None):
        payload = super().__request(relative_url).decode("UTF-8")
        self.payload = payload
        return payload

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

    def __request(self, action, api, kwargs):
        if not self._access_token:
            raise NotAuthorized

        # hack for https://github.com/WeCase/WeCase/issues/119
        if (api == "statuses/user_timeline" and self._authorize_code):
            if "uid" in kwargs and "screen_name" not in kwargs:
                kwargs["screen_name"] = self.api("users/show").get(uid=kwargs["uid"]).get("screen_name")
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
            result_json = json.loads(result)
            if not result_json:
                result_json = {}
            assert isinstance(result_json, dict)
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

    WEIBO_DOMAIN = "api.weibo.com"

    OAUTH2_PARAMETER = {
        'response_type': 'code',
        'action': 'submit',
        'isLoginSina': 0,
        'from': '',
        'regCallback': '',
        'state': '',
        'ticket': '',
        'withOfficalFlag': 0
    }

    AUTHORIZE_URL = "https://%s/oauth2/authorize" % WEIBO_DOMAIN
    ACCESS_TOKEN_URL = "https://%s/oauth2/access_token" % WEIBO_DOMAIN

    def __init__(self, username, password):
        self._username = username
        self._password = password
        self.authorize_code = ""

    def _request_authorize_code(self, application):
        oauth2 = self.OAUTH2_PARAMETER
        oauth2['client_id'] = application.app_key
        oauth2['redirect_uri'] = application.redirect_uri
        oauth2['userId'] = self._username
        oauth2['passwd'] = self._password

        curl = _Curl()
        curl.set_option(pycurl.FOLLOWLOCATION, False)  # don't follow redirect
        curl.set_option(pycurl.REFERER, self.AUTHORIZE_URL)  # required for auth
        try:
            curl.post(self.AUTHORIZE_URL, oauth2)
        except pycurl.error:
            raise NetworkError

        # After post the OAUTH2 information, if success,
        # Sina will return "302 Moved Temporarily", the target is "http://redirect_uri/?code=xxxxxx",
        # xxxxxx is the authorize code.
        redirect_url = curl.get_info(pycurl.REDIRECT_URL)
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
        result = curl.post(self.ACCESS_TOKEN_URL, access_token_parameter)
        return json.loads(result)["access_token"]

    def auth(self, application):
        authorize_code = self._request_authorize_code(application)
        return self._request_access_token(application, authorize_code)
