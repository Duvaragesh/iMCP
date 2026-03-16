"""Management command: run reachability health checks for all enabled iMCP services."""
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run reachability health checks for all enabled iMCP services."

    def add_arguments(self, parser):
        parser.add_argument(
            "--service",
            type=int,
            metavar="ID",
            help="Check only the service with this ID (default: all enabled services).",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print detailed results for each service.",
        )

    def handle(self, *args, **options):
        from imcp.models.service import Service
        from imcp.services.health_checker import check_service_reachability

        service_id = options.get("service")
        verbose = options.get("verbose")

        qs = Service.objects.filter(enabled=True)
        if service_id:
            qs = qs.filter(pk=service_id)

        services = list(qs.order_by("name"))

        if not services:
            self.stdout.write(self.style.WARNING("No enabled services found."))
            return

        self.stdout.write(f"Running health checks for {len(services)} service(s)...\n")

        passed = 0
        failed = 0

        for service in services:
            try:
                result = check_service_reachability(service)
                info = result.to_dict()
                reachable = info.get("reachable", False)
                latency = info.get("latency_ms")
                error = info.get("error")

                if reachable:
                    passed += 1
                    msg = f"  [OK]   {service.name}"
                    if latency is not None:
                        msg += f"  ({latency}ms)"
                    self.stdout.write(self.style.SUCCESS(msg))
                else:
                    failed += 1
                    msg = f"  [FAIL] {service.name}"
                    if error:
                        msg += f"  — {error}"
                    self.stdout.write(self.style.ERROR(msg))

                if verbose:
                    self.stdout.write(f"         URL: {service.url}")
                    self.stdout.write(f"         Type: {service.spec_type}")

            except Exception as exc:
                failed += 1
                self.stdout.write(
                    self.style.ERROR(f"  [ERROR] {service.name} — {exc}")
                )
                logger.exception(f"Health check raised for service {service.id}")

        self.stdout.write("")
        self.stdout.write(
            f"Results: {passed} OK, {failed} failed out of {len(services)} services."
        )

        if failed > 0:
            raise SystemExit(1)
