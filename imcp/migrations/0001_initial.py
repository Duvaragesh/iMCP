"""Initial migration for the iMCP Django app.

Creates four tables:
  - imcp_services
  - imcp_audit_events
  - imcp_tool_cache_metadata
  - imcp_api_keys
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        # ------------------------------------------------------------------
        # imcp_services
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="Service",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(db_index=True, max_length=255, unique=True)),
                ("spec_type", models.CharField(
                    choices=[("WSDL", "WSDL"), ("OpenAPI", "OpenAPI"), ("MCP_JSON", "MCP JSON")],
                    max_length=50,
                )),
                ("url", models.TextField()),
                ("category", models.CharField(db_index=True, max_length=100)),
                ("auth_type", models.CharField(
                    blank=True,
                    choices=[("Bearer", "Bearer Token"), ("Basic", "Basic Auth"), ("Custom", "Custom")],
                    max_length=50,
                    null=True,
                )),
                ("enabled", models.BooleanField(db_index=True, default=True)),
                ("allowlist", models.JSONField(blank=True, null=True)),
                ("denylist", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "imcp_services",
                "app_label": "imcp",
            },
        ),

        # ------------------------------------------------------------------
        # imcp_audit_events
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="AuditEvent",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("timestamp", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("actor", models.CharField(db_index=True, max_length=255)),
                ("action", models.CharField(db_index=True, max_length=100)),
                ("service_id", models.IntegerField(blank=True, db_index=True, null=True)),
                ("tool_name", models.CharField(blank=True, db_index=True, max_length=255, null=True)),
                ("status", models.CharField(db_index=True, max_length=50)),
                ("correlation_id", models.CharField(db_index=True, max_length=36, unique=True)),
                ("latency_ms", models.IntegerField(blank=True, null=True)),
                ("details", models.JSONField(blank=True, null=True)),
            ],
            options={
                "db_table": "imcp_audit_events",
                "app_label": "imcp",
            },
        ),

        # ------------------------------------------------------------------
        # imcp_tool_cache_metadata
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="ToolCacheMetadata",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("service", models.ForeignKey(
                    db_index=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    to="imcp.service",
                )),
                ("spec_hash", models.CharField(max_length=64)),
                ("generated_at", models.DateTimeField(auto_now_add=True)),
                ("ttl", models.IntegerField()),
                ("tools_json", models.JSONField()),
            ],
            options={
                "db_table": "imcp_tool_cache_metadata",
                "app_label": "imcp",
            },
        ),

        # ------------------------------------------------------------------
        # imcp_api_keys
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="APIKey",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key_hash", models.CharField(db_index=True, max_length=64, unique=True)),
                ("key_prefix", models.CharField(max_length=16)),
                ("name", models.CharField(max_length=100)),
                ("user_id", models.CharField(db_index=True, max_length=100)),
                ("roles", models.JSONField(default=list)),
                ("enabled", models.BooleanField(default=True)),
                ("revoked", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("description", models.TextField(blank=True, null=True)),
            ],
            options={
                "db_table": "imcp_api_keys",
                "app_label": "imcp",
            },
        ),
    ]
