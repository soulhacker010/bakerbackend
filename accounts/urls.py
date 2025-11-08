from django.urls import path

from .views import (
    FeedbackSubmissionView,
    LoginView,
    PasswordResetCompleteView,
    PasswordResetRequestView,
    PasswordResetValidateView,
    ProfileView,
    SignupView,
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
]
