RateLimit
==========

Distributed rate limit decorator/context manager for TornadoWeb applications
over Redis.


API
======


```python
from rate_limit import RateLimit, And, Or
import tornadoredis


redis_conn = tornadoredis.Client()
redis_conn.connect()
rl = RateLimit(redis_conn, namespace="my_namespace")

@rl.limit('10/s')
def do_stuff():
    """
    do_stuff() will only run 10 times per second,
    then an exception will be thrown
    """
    pass

```

Create more complex rules by using And and Or

```python
@rl.limit(Or('10/s', '15/m'))
def do_stuff():
    """
    do_stuff() will only run 10 times per second,
    or 15 times per minute, whatever happens first
    """
    pass
```

Or even more complex

```python
@rl.limit(And('apikey:100/h', Or('10/s', And('15/m', 'apikey:5/s:0.1'))), apikey=get_api_key)
def do_stuff():
    """
    same as before, but only start limiting do_stuff() when apikey
    limit of 100 requests an hour is reached.
    """
    pass
```

If you need to rate limit based on other selectors, such as username, apikey,
ip address and etc, you specify the selector's name in the rule, and pass
a keyword argument with the same name.

The argument could be a function or the literal value.

```python
def get_username(): pass

@rl.limit('username:10/5m', username=get_username)
def do_stuff():
    """
    this means each user can run do_stuff() 10 times in 5 minutes
    """
    pass

def get_api_key(): pass


@rl.limit(And('username:10/5m', 'apikey:100/m'), username=get_username, apikey=get_api_key)
def do_stuff():
    """
    do_stuff() will throw when user reached the 10 requests per 5 minute limit
    AND his API key reached 100 requests per minute, crazy.
    """
    pass
```

Well, this seems kinda long, so instead you could pass an object that has
the correspoding selectors as members or callable methods.

```python
class API(object):
    def apikey(self): pass
    def username(self): pass


@rl.limit(And('username:10/5m', 'apikey:100/m'), selector=API())
def do_stuff():
    """
    this is the same as before, but prettier
    """
    pass
```

If no selectors/selector is passed, and you're limiting on more than the
method name, it's assumed you're applying the decorator on a bound instance.

```python
class MyAPI(API):
    @rl.limit(And('username:10/5m', 'apikey:100/m'))
    def do_stuff(self):
        """
        the decorator will look for username and apikey in 'self'
        so you better have those!!!
        """
        pass
```

Usually when using a decorator you're limiting the rate of the decorated
function, thus function name is used, but sometimes you want a limit across
mulltiple functions, you can use the 'key' argument for that

In the following example, good_kittie and bad_kittie share the same rate limit
counters, username and apikey. you just have to make sure they're defined
in the correct order.

```python
@rl.limit(And('username:10/5m', 'apikey:100/m'), selector=API(), key='cats')
def good_kittie(): pass

@rl.limit(key='cats')
def good_kittie(): pass
```

Context Managers:
==================

Most decorator stuff applies also to contextmanager, with two differences:

1. There's no 'self', so you have to pass a 'selector' object, or individual
selectors like in the first examples

2. 'key' is empty by default, so rate limits are global, meaning
if you're limiting username:10/s then all context managers with that limit
will share the same limit, so you might want to pass that 'key' argument.

Examples:

```python
with (yield rl.limit('username:10/5m', username=get_username).cm):
    do_stuff()

with (yield rl.limit('username:10/5m', username=get_username, key='login').cm):
    do_stuff()
```

Api Caveats
=======

1. Unless 'key' argument given, function name is used to tell apart from
   from different rate limits, i.e when decorating function do_stuff() the name
   do_stuff (+selector_name+selector_value) is used to identify the rate limit.

   Since the underlying data layer is usually shared, there would be a collisoin
   if someone else defines a do_stuff function and uses the same rate limit,
   to avoid this collaboration mess, you can use the 'namespace' argument to the
   RateLimit constructor, or use the 'key' argument to the decorator/CM.

2. Decorated functions become coroutines, so after decoration they return
   a Future object, and should be invoked with yield.
   

Internals
=========

Rate Limiting Algorithm
=======================

terms:
======

* ```key```: the key keyword argument passed to limit() or the name of the decorated method.
* ```selector_name```: the literal 'username' or 'ipaddress', could be empty if limiting the rate of function calls
* ```selector_value```: the actual username, ("vova666"), or the ipaddress ("8.8.8.8")
* ```namespace```: a per project set string to avoid collisions with other users on the same Redis
* ```idetifier```: the combination of all of the above: namespace:key:selecor_name:selector_value, where last two could be empty
* ```allowed_requests```: integer indicating how much requests are allowed
* ```requests_span```: on how much time ```allowed_requests``` can span, in the format of s, m, 100s, 1m, 24h, etc
* ```rate```: a string with a ```allowed_requests```/```requests_span``` format, e.g 100/m (100 requests per minute)
* ```rule```: ```selector_name```:```rate```, e.g user:100/m, user "vova666" can do 100 requests per minute.

insertation:
============

0. figure out the ```max_allowed_requests``` and ```max_requests_span``` for the ```identifier```
   e.g, if two rules share the same ```identifier```, like: user:10/s and user:100/h, 
   ```max_allowed_requests``` will be 100, and ```max_requests_span``` will be 3600 seconds.

1. ```LPUSH``` the current timestamp at the head of the ```identifier``` list

2. ```LTRIM``` the ```identifier``` list to the size of ```max_allowed_requests```, basically removing the last element

3. ```EXPIRE``` the ```identifier```s list with ```max_requests_span```

NOTE: we're affectivaly poping on element from the tail, and pushing one to the head, so it's O(1)


lookup:
=======

say you want to know if rate limit of 100/m has been reached:

1. ```LINDEX``` the 100th element of the ```idetifier``` list

2. if ```time()``` - ```100th element timestamp``` is less than 60 seconds,
it means the limit has been reached.

NOTE: ```LINDEX``` is O(N) complexity unless the element in question is
the first or last element and in that case it's O(1). depending on the usage pattern
and defined rules, this could be geared to O(1) most of the time.


rule resolving:
==============

a ```rule``` could be something simple like '10/s' or something complex with
combination or logical operators, e.g: Or('10/s', And('user:100/h', 'apikey:60/h')
this rules means limit to 10 calls per second, OR when both a user reached
100 requests an hour, AND an apikey reached 60 requests an hour.

resolving stops on the first limit reached, if 10/s reached, it won't check the other rules.

logging requests:
=================

when a request allows to go through, all associated ```selectors```s needs to 
be updated, so for the above example, we log the timestamp for the call itself,
the user and the apikey.

entire flow:
============

1. ```LOCK``` the ```key``` (more on locking below)
2. resolve rules, if a rate limit matched, skip next step
3. log request to all ```selectors```
4. ```UNLOCK```
5. return result, rate limit reached or not.

locking:
========

locking can be disabled by passing ```disable_locks``` to the ```RateLimit```
constructor, to gain performance and risk race conditions.

locking is needed when we want to avoid the following situation:
says we have the following rule: ```Or('user:100/h', 'apikey:60/h')```, we check
the limits on the ```user``` rule, all fine, then while we're checking the
```apikey``` rule, the user makes another request, and effectivly reaches the limit,
the ```apikey``` is also fine, so we let a user who reached the limit, pass.

this could be avoided with at least two ways: (NOT IMPLEMENTED)

1. this is a problem only with multiple ```selectors``` on the same ```key```,
   if it's just one ```selector``` we could easily do the checking and logging
   as one atomic operation. 

2. another option is to move the entire logic (+rule resolving) into a ```LUA```
   script and have redis execute it as one command.


trade-offs:
==========

it seems it's all about the tradeoffs.

PROS:
=====
0. simple, easy to understand algorithm

1. accuracy, we know the time stamp of each request.

2. can apply many rules on the same ```identifier```, can dynamically change the
   number or requests allowed and the time span and apply multiple rules on the
   same list.

3. can piggy back more data on that list, for example instead of just holding
   the timestamp, we could also log amount of transfared bytes of that request
   and could how many bytes were transfare in the last N request/time
   but this is O(N)

4. it should be easy to ```SHARD``` based on ```identifier``` string

5. since the window of time shifts, we don't have the problem of someone
   doing 100 request in the few seconds of the hour, and then another
   100 in the first seconds of the new hour.

5. depending on usage, could be O(1) time complexity.


CONS:
=====

1. space complexity: logging each query could get expensive, but it really depends
   on the usage pattern, e.g if you have many users and each does a couple requests,
   you'll have the cost of ```LIST``` struct and a couple of timestamps, limited
   to the number of ```allowed_requests```, in another case when limiting just
   the function call itself with no selector, say '1000/s', it's 1000 * cost of
   storing a timestamp, which fits in an INT, so it's 4MB or 8MB depending on
   32/64 bit and the cost of the list overhead.

2. lookup could be O(N) in some cases, e.g when you have multiple rate limits
   on the same ```identifier```, and you have more logged requests than its ```allowed_requests```
   because the other rule has more ```allowed_requests``` but it's rate limit didn't reach.

3. no burstiness control. but since we're storing a time series,
   maybe it's possible to implement on top of this structure.

4. have to hit Redis every single time, for single rules it's possible to implement
   a local expiry cache, since we know how much time should pass until it's less than ```requests_span```
   but it's more tricky with multiple rules.

5. all clocks have to be synched.
