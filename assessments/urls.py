from rest_framework.routers import DefaultRouter
from rest_framework.urls import path

from .views import (
    AssessmentCategoryViewSet,
    AssessmentResponseViewSet,
    AssessmentTagViewSet,
    AssessmentViewSet,
    RespondentAssessmentDetailView,
    RespondentAssessmentResponseView,
    RespondentLinkClientView,
    RespondentLinkEmailInviteView,
    RespondentLinkIssueView,
    RespondentLinkResolveView,
    RespondentLinkScheduleRunListView,
    RespondentLinkScheduleDetailView,
    RespondentLinkScheduleView,
)

app_name = "assessments"

router = DefaultRouter()
router.register(r"assessments", AssessmentViewSet, basename="assessment")
router.register(r"assessment-categories", AssessmentCategoryViewSet, basename="assessment-category")
router.register(r"assessment-tags", AssessmentTagViewSet, basename="assessment-tag")
router.register(r"assessment-responses", AssessmentResponseViewSet, basename="assessment-response")

urlpatterns = router.urls + [
    path("respondent-links/issue/", RespondentLinkIssueView.as_view(), name="respondent-link-issue"),
    path("respondent-links/resolve/", RespondentLinkResolveView.as_view(), name="respondent-link-resolve"),
    path("respondent-links/client/", RespondentLinkClientView.as_view(), name="respondent-link-client"),
    path("respondent-links/email/", RespondentLinkEmailInviteView.as_view(), name="respondent-link-email"),
    path("respondent-links/schedule/", RespondentLinkScheduleView.as_view(), name="respondent-link-schedule"),
    path(
        "respondent-links/schedule/runs/",
        RespondentLinkScheduleRunListView.as_view(),
        name="respondent-link-schedule-runs",
    ),
    path(
        "respondent-links/schedule/<uuid:reference>/",
        RespondentLinkScheduleDetailView.as_view(),
        name="respondent-link-schedule-detail",
    ),
    path("respondent-links/assessment/", RespondentAssessmentDetailView.as_view(), name="respondent-link-assessment"),
    path(
        "respondent-links/assessment-response/",
        RespondentAssessmentResponseView.as_view(),
        name="respondent-link-assessment-response",
    ),
]
