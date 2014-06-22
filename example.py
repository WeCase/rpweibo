#!/usr/bin/env python3


import rpweibo
from pprint import pprint


wecase = rpweibo.Application("1011524190",
                             "1898b3f668368b9f4a6f7ac8ed4a918f",
                             'https://api.weibo.com/oauth2/default.html')

username = input("Please enter your username: ")
password = input("Please enter your password: ")

authenticator = rpweibo.UserPassAutheticator(username, password)
weibo = rpweibo.Weibo(wecase)

try:
    weibo.auth(authenticator)
except rpweibo.AuthorizeFailed:
    print("Wrong password!")

tweets = weibo.get("statuses/user_timeline")["statuses"]
for tweet in tweets:
    pprint(tweet)

weibo.post("statuses/update", status="Hello, world!")
