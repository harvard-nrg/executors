import os
import re

def which(x):
    for p in os.environ.get('PATH').split(os.pathsep):
        p = os.path.join(p, x)
        if os.path.exists(p):
            return os.path.abspath(p)
    return None

def match(s, expressions):
    for expr in expressions:
        if re.match(s, expr):
            return True
    return False
