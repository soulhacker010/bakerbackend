from django.urls import path

from .views import (
    AllUsersView,
    ApproveUserView,
    FeedbackSubmissionView,
    LoginView,
    LogoutView,
    PasswordResetCompleteView,
    PasswordResetRequestView,
    PasswordResetValidateView,
    PendingUsersView,
    ProfileView,
    RejectUserView,
    SignupView,
    ToggleUserActiveView,
    TokenRefreshView,
    TwoFactorResendView,
    TwoFactorVerifyView,
)

app_name = "accounts"

urlpatterns = [
    path("signup/", SignupView.as_view(), name="signup"),
    path("login/", LoginView.as_view(), name="login"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("feedback/", FeedbackSubmissionView.as_view(), name="feedback"),
    path("password/reset/request/", PasswordResetRequestView.as_view(), name="password-reset-request"),
    path("password/reset/validate/", PasswordResetValidateView.as_view(), name="password-reset-validate"),
    path("password/reset/complete/", PasswordResetCompleteView.as_view(), name="password-reset-complete"),
    path("2fa/verify/", TwoFactorVerifyView.as_view(), name="two-factor-verify"),
    path("2fa/resend/", TwoFactorResendView.as_view(), name="two-factor-resend"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    # Admin approval endpoints
    path("pending-users/", PendingUsersView.as_view(), name="pending-users"),
    path("approve-user/", ApproveUserView.as_view(), name="approve-user"),
    path("reject-user/", RejectUserView.as_view(), name="reject-user"),
    # Admin user management endpoints
    path("all-users/", AllUsersView.as_view(), name="all-users"),
    path("toggle-user-active/", ToggleUserActiveView.as_view(), name="toggle-user-active"),
]
