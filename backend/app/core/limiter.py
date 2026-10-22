"""
Rate limiting via slowapi (Flask-Limiter-style API for FastAPI/Starlette).
Protects auth and OTP endpoints from brute force / abuse.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
