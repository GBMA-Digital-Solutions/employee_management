import hashlib
import secrets
from collections import defaultdict
from datetime import datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .accounts import employee_record
from .models import (ActivityClassification, ActivityEvent, AttendanceVisit, Employee,
                     MonitoringAgent, MonitoringConsent)
from .permissions import business_id_for, can_manage


DISCLOSURE = (
    "During configured working hours, your employer may collect the websites and desktop applications "
    "used on an authorized work device and the time spent on each. The system does not collect private "
    "messages, passwords, keystrokes, form contents, URL query values, or screenshots."
)
FORBIDDEN_FIELDS = {"password", "passwords", "keystrokes", "keys", "screenshot", "screenshots",
                    "message", "messages", "clipboard", "form_data", "content", "window_title"}


def employer_business(request):
    if not can_manage(request.user) or business_id_for(request.user) is None:
        raise PermissionDenied("Only a company employer can access detailed activity monitoring.")
    return business_id_for(request.user)


def normalize_domain(value):
    value = value.strip().lower().rstrip(".")
    if not value or "/" in value or ":" in value or len(value) > 253:
        raise serializers.ValidationError("Enter a hostname such as example.com.")
    return value


def category_map(business_id):
    return dict(ActivityClassification.objects.filter(business_id=business_id).values_list("domain", "category"))


def category_for(domain, mapping):
    domain = domain.lower()
    matches = [(key, value) for key, value in mapping.items()
               if domain == key or domain.endswith(f".{key}")]
    return max(matches, key=lambda item: len(item[0]))[1] if matches else "other"


class MonitoringDisclosureView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        employee = employee_record(request.user)
        if not employee:
            raise PermissionDenied("Your account is not linked to an employee record.")
        consent, _ = MonitoringConsent.objects.get_or_create(employee=employee)
        return Response({"notice": DISCLOSURE, "acknowledged_at": consent.acknowledged_at})

    def post(self, request):
        employee = employee_record(request.user)
        if not employee:
            raise PermissionDenied("Your account is not linked to an employee record.")
        if request.data.get("acknowledged") is not True:
            raise serializers.ValidationError({"acknowledged": "Confirm that you have read the disclosure."})
        consent, _ = MonitoringConsent.objects.get_or_create(employee=employee)
        consent.acknowledged_at = timezone.now()
        consent.save(update_fields=["acknowledged_at"])
        return Response({"notice": DISCLOSURE, "acknowledged_at": consent.acknowledged_at})


class AgentIssueView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, employee_id):
        business_id = employer_business(request)
        employee = Employee.objects.filter(pk=employee_id, business_id=business_id, is_active=True).first()
        if not employee:
            raise NotFound("No employee matches the given query.")
        consent = MonitoringConsent.objects.filter(employee=employee, acknowledged_at__isnull=False).first()
        if not consent:
            raise serializers.ValidationError("The employee must acknowledge the monitoring disclosure first.")
        raw = secrets.token_urlsafe(32)
        agent, _ = MonitoringAgent.objects.update_or_create(
            employee=employee,
            defaults={"token_hash": hashlib.sha256(raw.encode()).hexdigest(), "is_active": True,
                      "issued_at": timezone.now()},
        )
        return Response({"employee": employee.pk, "token": raw, "issued_at": agent.issued_at,
                         "detail": "Copy this token now. It is shown only once."})

    def delete(self, request, employee_id):
        business_id = employer_business(request)
        updated = MonitoringAgent.objects.filter(employee_id=employee_id,
                                                  employee__business_id=business_id).update(is_active=False)
        if not updated:
            raise NotFound("No monitoring agent matches the given query.")
        return Response(status=status.HTTP_204_NO_CONTENT)


class IngestThrottle(AnonRateThrottle):
    rate = "240/min"


class ActivityIngestSerializer(serializers.Serializer):
    source = serializers.ChoiceField(choices=["windows", "browser"])
    kind = serializers.ChoiceField(choices=["application", "website"])
    resource = serializers.CharField(max_length=1000, trim_whitespace=True)
    started_at = serializers.DateTimeField()
    ended_at = serializers.DateTimeField()

    def validate(self, attrs):
        unexpected = set(self.initial_data) - set(self.fields)
        sensitive = unexpected & FORBIDDEN_FIELDS
        if sensitive:
            raise serializers.ValidationError(
                f"Sensitive monitoring fields are forbidden: {', '.join(sorted(sensitive))}.")
        if unexpected:
            raise serializers.ValidationError(f"Unknown fields are not accepted: {', '.join(sorted(unexpected))}.")
        start, end = attrs["started_at"], attrs["ended_at"]
        seconds = (end - start).total_seconds()
        if seconds <= 0 or seconds > 15 * 60:
            raise serializers.ValidationError("Each activity interval must be between 1 second and 15 minutes.")
        if end > timezone.now() + timedelta(minutes=1):
            raise serializers.ValidationError("Activity cannot be recorded in the future.")
        if attrs["kind"] == "website":
            parsed = urlsplit(attrs["resource"] if "://" in attrs["resource"] else f"https://{attrs['resource']}")
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise serializers.ValidationError({"resource": "Enter a valid HTTP or HTTPS website."})
            attrs["domain"] = parsed.hostname.lower().rstrip(".")
            # Queries/fragments often contain searches, tokens, message text, or form values.
            attrs["resource"] = urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", "", ""))[:500]
        else:
            attrs["domain"] = ""
            attrs["resource"] = attrs["resource"][:200]
        return attrs


def within_configured_work(employee, start, end):
    visit = AttendanceVisit.objects.filter(
        attendance__employee=employee, check_in_at__lte=start,
    ).filter(Q(check_out_at__isnull=True) | Q(check_out_at__gte=end)).first()
    if not visit:
        return False
    business = employee.business
    if not (business.workday_start and business.workday_end):
        return True
    local_start, local_end = timezone.localtime(start), timezone.localtime(end)
    if local_start.date() != local_end.date() and business.workday_end > business.workday_start:
        return False
    start_time, end_time = local_start.time().replace(tzinfo=None), local_end.time().replace(tzinfo=None)
    if business.workday_end > business.workday_start:
        return start_time >= business.workday_start and end_time <= business.workday_end
    return start_time >= business.workday_start or end_time <= business.workday_end


class ActivityIngestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [IngestThrottle]

    def post(self, request):
        raw = request.headers.get("X-Monitoring-Agent-Token", "")
        digest = hashlib.sha256(raw.encode()).hexdigest()
        agent = MonitoringAgent.objects.select_related("employee__business").filter(
            token_hash=digest, is_active=True, employee__is_active=True,
            employee__monitoring_consent__acknowledged_at__isnull=False,
        ).first()
        if not raw or not agent:
            return Response({"detail": "Invalid or revoked monitoring agent token."}, status=401)
        serializer = ActivityIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not within_configured_work(agent.employee, data["started_at"], data["ended_at"]):
            raise PermissionDenied("Activity is accepted only during recorded and configured working hours.")
        event = ActivityEvent.objects.create(
            employee=agent.employee, source=data["source"], kind=data["kind"],
            resource=data["resource"], domain=data["domain"], started_at=data["started_at"],
            ended_at=data["ended_at"], duration_seconds=int((data["ended_at"] - data["started_at"]).total_seconds()),
        )
        agent.last_seen_at = timezone.now()
        agent.save(update_fields=["last_seen_at"])
        return Response({"id": event.pk, "accepted": True}, status=201)


class ClassificationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        business_id = employer_business(request)
        domain = normalize_domain(str(request.data.get("domain", "")))
        category = request.data.get("category")
        if category not in dict(ActivityClassification.CATEGORIES):
            raise serializers.ValidationError({"category": "Choose work, social, entertainment, or other."})
        row, _ = ActivityClassification.objects.update_or_create(
            business_id=business_id, domain=domain, defaults={"category": category})
        return Response({"id": row.pk, "domain": row.domain, "category": row.category})


class ActivityReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        business_id = employer_business(request)
        employees = Employee.objects.filter(business_id=business_id, is_active=True).select_related(
            "monitoring_consent", "monitoring_agent").order_by("first_name", "last_name")
        employee_id = request.query_params.get("employee")
        period = request.query_params.get("period", "daily")
        if period not in {"daily", "weekly", "monthly"}:
            raise serializers.ValidationError({"period": "Choose daily, weekly, or monthly."})
        try:
            selected_date = datetime.strptime(request.query_params.get("date", str(timezone.localdate())), "%Y-%m-%d").date()
        except ValueError:
            raise serializers.ValidationError({"date": "Use YYYY-MM-DD."})
        if period == "daily":
            start_date, end_date = selected_date, selected_date
        elif period == "weekly":
            start_date = selected_date - timedelta(days=selected_date.weekday())
            end_date = start_date + timedelta(days=6)
        else:
            start_date = selected_date.replace(day=1)
            next_month = (start_date.replace(day=28) + timedelta(days=4)).replace(day=1)
            end_date = next_month - timedelta(days=1)
        zone = timezone.get_current_timezone()
        start = timezone.make_aware(datetime.combine(start_date, datetime.min.time()), zone)
        end = timezone.make_aware(datetime.combine(end_date + timedelta(days=1), datetime.min.time()), zone)
        events = ActivityEvent.objects.filter(employee__business_id=business_id,
                                              started_at__gte=start, started_at__lt=end)
        selected = None
        if employee_id:
            selected = employees.filter(pk=employee_id).first()
            if not selected:
                raise NotFound("No employee matches the given query.")
            events = events.filter(employee=selected)
        mapping = category_map(business_id)
        resource_totals, category_totals, day_totals = defaultdict(int), defaultdict(int), defaultdict(int)
        timeline = []
        for event in events.select_related("employee")[:2000]:
            category = category_for(event.domain, mapping) if event.kind == "website" else "other"
            resource_totals[(event.kind, event.resource, event.domain, category)] += event.duration_seconds
            category_totals[category] += event.duration_seconds
            day_totals[str(timezone.localtime(event.started_at).date())] += event.duration_seconds
            timeline.append({"id": event.pk, "employee": event.employee_id,
                             "employee_name": str(event.employee), "source": event.source, "kind": event.kind,
                             "resource": event.resource, "domain": event.domain, "category": category,
                             "started_at": event.started_at, "ended_at": event.ended_at,
                             "duration_seconds": event.duration_seconds})
        resources = [{"kind": key[0], "resource": key[1], "domain": key[2], "category": key[3],
                      "duration_seconds": value} for key, value in resource_totals.items()]
        resources.sort(key=lambda row: row["duration_seconds"], reverse=True)
        return Response({
            "employees": [{"id": row.pk, "name": str(row), "department": row.department,
                           "consent": bool(getattr(row, "monitoring_consent", None)
                                           and row.monitoring_consent.acknowledged_at),
                           "agent_active": bool(getattr(row, "monitoring_agent", None)
                                                and row.monitoring_agent.is_active),
                           "agent_last_seen_at": (row.monitoring_agent.last_seen_at
                                                  if getattr(row, "monitoring_agent", None) else None)}
                          for row in employees],
            "selected_employee": selected.pk if selected else None, "period": period,
            "start_date": start_date, "end_date": end_date,
            "total_seconds": sum(category_totals.values()),
            "categories": [{"category": key, "duration_seconds": category_totals.get(key, 0)}
                           for key in ("work", "social", "entertainment", "other")],
            "resources": resources, "days": [{"date": key, "duration_seconds": value}
                                               for key, value in sorted(day_totals.items())],
            "timeline": timeline,
            "classifications": [{"domain": key, "category": value} for key, value in sorted(mapping.items())],
            "privacy_notice": DISCLOSURE,
        })
