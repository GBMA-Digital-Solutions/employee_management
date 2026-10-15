from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (EmployeeViewSet, ContractViewSet, AttendanceViewSet, LeaveBalanceViewSet, LeaveViewSet,
                    HolidayViewSet, AnnouncementViewSet, CalendarEventViewSet,
                    SalaryViewSet, PayrollViewSet, ManagerReportsView)
from .payroll_views import (AssetIncidentViewSet, PayrollCalculationViewSet, PayrollPolicyView,
                            SalaryAdvanceRequestViewSet, SalaryAdvanceViewSet)
from .workplace import WorkplaceLocationView
from .access_control import (RoomAccessGrantViewSet, RoomAccessHistoryViewSet, RoomPermissionChangeViewSet,
                             RoomUnlockView, RoomViewSet)
from .door_simulator import DoorSimulatorView
from .activity_monitoring import (ActivityIngestView, ActivityReportView, AgentIssueView,
                                  ClassificationView, MonitoringDisclosureView)

router = DefaultRouter()
router.register("employees", EmployeeViewSet)
router.register("contracts", ContractViewSet)
router.register("attendance", AttendanceViewSet)
router.register("leave", LeaveViewSet)
router.register("leave-balances", LeaveBalanceViewSet)
router.register("holidays", HolidayViewSet)
router.register("announcements", AnnouncementViewSet)
router.register("calendar-events", CalendarEventViewSet)
router.register("salaries", SalaryViewSet)
router.register("payroll", PayrollViewSet)
router.register("payroll-calculations", PayrollCalculationViewSet, basename="payroll-calculation")
router.register("salary-advances", SalaryAdvanceViewSet)
router.register("salary-advance-requests", SalaryAdvanceRequestViewSet, basename="salary-advance-request")
router.register("asset-incidents", AssetIncidentViewSet)
router.register("access-control/rooms", RoomViewSet, basename="room")
router.register("access-control/grants", RoomAccessGrantViewSet, basename="room-access-grant")
router.register("access-control/permission-changes", RoomPermissionChangeViewSet, basename="room-permission-change")
router.register("access-control/history", RoomAccessHistoryViewSet, basename="room-access-history")

urlpatterns = [path("reports/", ManagerReportsView.as_view(), name="manager-reports"),
               path("activity-monitoring/", ActivityReportView.as_view(), name="activity-monitoring"),
               path("activity-monitoring/classifications/", ClassificationView.as_view(), name="activity-classifications"),
               path("activity-monitoring/agents/<int:employee_id>/", AgentIssueView.as_view(), name="activity-agent"),
               path("activity-monitoring/ingest/", ActivityIngestView.as_view(), name="activity-ingest"),
               path("me/monitoring-disclosure/", MonitoringDisclosureView.as_view(), name="monitoring-disclosure"),
               path("access-control/rooms/<int:pk>/unlock/", RoomUnlockView.as_view(), name="room-unlock"),
               path("access-control/simulator/<int:pk>/", DoorSimulatorView.as_view(), name="door-simulator"),
               path("workplace-location/", WorkplaceLocationView.as_view(), name="workplace-location"),
               path("payroll-policy/", PayrollPolicyView.as_view(), name="payroll-policy"),
               path("", include(router.urls))]
