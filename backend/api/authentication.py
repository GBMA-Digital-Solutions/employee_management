from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed


class SessionJWTAuthentication(JWTAuthentication):
    """JWT authentication with immediate server-side logout invalidation."""

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        profile = getattr(user, "account_profile", None)
        current = profile.token_version if profile else 0
        if validated_token.get("token_version", 0) != current:
            raise AuthenticationFailed("This session has been signed out.", code="session_revoked")
        return user
