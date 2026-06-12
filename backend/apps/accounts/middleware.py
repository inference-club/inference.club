"""Session-epoch enforcement.

Django has no native "log this user out everywhere". Each session stores the
user's ``session_epoch`` at login (see signals); bumping the user's epoch
(passcode revoke, guest revoke, future "log out all devices") makes every
live session mismatch and get logged out here. O(1) per request — no session
table scans.
"""

from django.contrib.auth import logout

SESSION_EPOCH_KEY = "session_epoch"


class SessionEpochMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            stored = request.session.get(SESSION_EPOCH_KEY)
            current = getattr(user, "session_epoch", 0)
            if stored is None:
                # Pre-feature session: adopt the current epoch rather than
                # logging everyone out on deploy.
                request.session[SESSION_EPOCH_KEY] = current
            elif stored != current:
                logout(request)
        return self.get_response(request)
