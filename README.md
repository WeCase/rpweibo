rpweibo
=======

cURL + Python Weibo Wrapper.


## Installing

    sudo python3 setup.py install

## Usage

### Initialize

    import rpweibo

    # initialize a Application
    example_app = rpweibo.Application(APP_KEY, APP_SECRET, REDIRECT_URI)
    weibo = rpweibo.Weibo(example_app)

### Authorize

#### with Username and Password

    authenticator = rpweibo.UserPassAutheticator(USERNAME, PASSWORD)
    weibo.auth(authenticator)

#### with Existing Access Token

    authenticator = rpweibo.AccessTokenAuthenticator(ACCESS_TOKEN)
    weibo.auth(authenticator)

### Using API

#### Procedural Style

    tweets = weibo.get("statuses/user_timeline")["statuses"]
    for tweet in tweets:
        print(tweets["text"])

    weibo.post("statuses/update", status="Hello, world!")

#### Object Style

    tweets = weibo.api("statuses/user_timeline).get().statuses
    for tweet in tweets:
        print(tweets.text)

    weibo.api("statuses/update").post("Hello, world!")
