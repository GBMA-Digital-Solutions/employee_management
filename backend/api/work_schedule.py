from datetime import datetime, timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Business
from .permissions import can_manage


class WorkScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Business
        fields = ["expected_daily_hours", "workday_start", "workday_end", "reminder_minutes"]

    def validate(self, attrs):
        start = attrs.get("workday_start", getattr(self.instance, "workday_start", None))
        end = attrs.get("workday_end", getattr(self.instance, "workday_end", None))
        if bool(start) != bool(end):
            raise serializers.ValidationError("Set both the workday start and end, or leave both blank.")
        return attrs


class WorkScheduleView(APIView):
    permission_classes = [IsAuthenticated]

    def business(self, request):
        if not can_manage(request.user):
            raise serializers.ValidationError("Only an employer can change company working hours.")
        profile = getattr(request.user, "account_profile", None)
        if not profile or not profile.business_id:
            raise serializers.ValidationError("Your account is not linked to a company.")
        return profile.business

    def get(self, request):
        return Response(WorkScheduleSerializer(self.business(request)).data)

    def patch(self, request):
        business = self.business(request)
        serializer = WorkScheduleSerializer(business, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


def expected_departure(attendance):
    """Return the configured departure time for this attendance workday."""
    business = attendance.employee.business
    zone = timezone.get_current_timezone()
    if business.workday_start and business.workday_end:
        result = timezone.make_aware(datetime.combine(attendance.date, business.workday_end), zone)
        if business.workday_end <= business.workday_start:
            result += timedelta(days=1)
        return result
    # For duration-based companies, time spent outside must not bring the
    # expected departure closer. Add the remaining work to the current time.
    return timezone.now() + timedelta(seconds=work_summary(attendance)["remaining_seconds"])


def work_summary(attendance, now=None):
    """Live completed and remaining work, excluding every temporary absence."""
    now = now or timezone.now()
    worked_seconds = 0
    for visit in attendance.visits.all():
        end = visit.check_out_at or now
        worked_seconds += max(0, (end - visit.check_in_at).total_seconds())
    expected_seconds = int(float(attendance.employee.business.expected_daily_hours or Decimal("8")) * 3600)
    remaining_seconds = max(0, expected_seconds - worked_seconds)
    return {
        "worked_seconds": int(worked_seconds),
        "remaining_seconds": int(remaining_seconds),
        "expected_seconds": expected_seconds,
    }
