"""Business-logic services.

API routers must talk to the database only through services here. This boundary
lets us swap implementations (e.g. identity encryption → AES-GCM on stage 7)
without touching API code.
"""
