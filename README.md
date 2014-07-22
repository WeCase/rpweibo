rpweibo
=======

cURL + Python Weibo Wrapper.


## Installing

```bash
sudo python3 setup.py install
```

## Usage

### Initialize

```python
import rpweibo

# initialize a Application
example_app = rpweibo.Application(APP_KEY, APP_SECRET, REDIRECT_URI)
weibo = rpweibo.Weibo(example_app)
```

### Authorize

#### with Username and Password

```python
authenticator = rpweibo.UserPassAutheticator(USERNAME, PASSWORD)
try:
    weibo.auth(authenticator)
except rpweibo.AuthorizeFailed:
    print("Invalid username or password!")
```

#### with Existing Access Token

```python
authenticator = rpweibo.AccessTokenAuthenticator(ACCESS_TOKEN)
weibo.auth(authenticator)
```

### Using API

#### Styles

##### Procedural Style

```python
tweets = weibo.get("statuses/user_timeline")["statuses"]
for tweet in tweets:
    print(tweets["text"])

weibo.post("statuses/update", status="Hello, world!")
```

##### Object Style

```python
tweets = weibo.api("statuses/user_timeline).get().statuses
for tweet in tweets:
    print(tweets.text)

weibo.api("statuses/update").post("Hello, world!")
```

### Error Handling

```python
try:
    tweets = weibo.api("statuses/user_timeline).get().statuses
except rpweibo.RemoteError:
    # handle API errors likely cause by remote server
    print("Something wrong with the server")
except rpweibo.CallerError:
    # handle API errors likely cause by the client
    print("You shouldn't use the API in this way")
except rpweibo.ResultCorrupted:
    print("Request the API successfully, but got the corrupted result")
except rpweibo.NetworkError:
    print("Somethings wrong with your network")
except rpweibo.APIError as e:
    # Handle all API errors, including RemoteError and CallerError.
    # NOTE: we handle both two type of API errors already, never reach here
    print("%d - %s" % (e.error_code, e.error_message))
```
