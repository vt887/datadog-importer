# JSON Template Best Practices

**Purpose:**  Detailed Recommendations for ABC_Monitoring Dashboards

---

## Directory Structure Analysis (example)

```
templates/
├── test_widget.json                    # Test fixture
└── abc_monitoring/
    ├── abc_monitoring.json             # Root/parent dashboard (groups only)
    ├── ambassador_overview/            # Sub-group 1
    ├── azure_logs_errors_overview/     # Sub-group 2
    ├── logs_errors_overview/           # Sub-group 3
    ├── management_overview/            # Sub-group 4
    ├── node_boot_time_per_shape_type_overview/  # Sub-group 5
    ├── pods_overview/                  # Sub-group 6
    ├── response_time_distribution/     # Sub-group 7
    └── shape_type_based_count_of_jobs/ # Sub-group 8
```

---

## Recommendations by Group

### 1. **Root Dashboard: abc_monitoring.json**

**Current State:**
- Contains only group definitions (widgets with empty arrays)
- Acts as container for sub-dashboards
- No metadata

**Recommendations:**

```json
{
  "title": "ABC_Monitoring",
  "description": "[[suggested_dashboards]] (cloned)",
  "_metadata": {
    "version": "1.0.0",
    "last_updated": "2025-10-29",
    "owner": "platform-team",
    "documentation": "https://wiki.company.com/dashboards/abc-monitoring",
    "slack_channel": "#platform-alerts",
    "runbook": "https://wiki.company.com/runbooks/abc-monitoring",
    "slos": {
      "availability": "99.9%",
      "response_time_p99": "500ms"
    }
  },
  "tags": ["abc", "monitoring", "infrastructure"],
  "layout_type": "ordered",
  "template_variables": [
    {
      "name": "cluster_name",
      "prefix": "cluster_name",
      "default": "*",
      "available_values": ["prod", "staging", "dev"]
    }
  ],
  "widgets": [
    // ...groups...
  ]
}
```

**Action Items:**
* Add `_metadata` section with version, owner, and documentation links
* Add `tags` for searchability
* Document template variables with available values
* Add SLO targets for reference

---

### 2. **Ambassador Overview Group**

**Current Files:**
- `abc_monitoring_ambassador_overview_ambassador_error_logs_for_abc.json`
- `abc_monitoring_ambassador_overview_ambassador_logs_for_abc.json`
- `abc_monitoring_ambassador_overview_ambassador_non_200_201_response_code.json`
- `abc_monitoring_ambassador_overview_ambassador_response_by_status_for_abc_non_200_201.json`
- `abc_monitoring_ambassador_overview_ambassador_response_by_status_for_abc.json`

**Recommendations:**

1. **Add Widget-Level Metadata:**
   ```json
   {
     "title": "ABC_Monitoring - Ambassador Overview - Ambassador Error Logs for ABC",
     "_widget_metadata": {
       "purpose": "Display error logs from Ambassador proxy in ABC cluster",
       "metric_type": "logs",
       "data_source": "logs_stream",
       "owner": "platform-team",
       "alert_threshold": null,
       "depends_on": ["cluster_name"],
       "query_explanation": "Filters for Ambassador pods in ABC namespace, excludes successful responses (200/201)"
     },
     "description": "[[suggested_dashboards]] (cloned)",
     "widgets": [...]
   }
   ```

2. **Standardize Query Documentation:**
   - Add inline comments explaining query logic
   - Document filter criteria
   - Link to metric definitions

3. **Add Response Status Breakdown:**
   - Create a summary widget showing response code distribution
   - Include 4xx vs 5xx breakdown
   - Add latency percentiles

---

### 3. **Azure Logs Errors Overview Group**

**Current Files:**
- `abc_monitoring_azure_logs_errors_overview_all_batcherrorexception.json`
- `abc_monitoring_azure_logs_errors_overview_all_errors.json`
- `abc_monitoring_azure_logs_errors_overview_batcherrorexception_with_operationtimedout_resizing.json`
- `abc_monitoring_azure_logs_errors_overview_nodes_in_not_running_or_idle_state.json`

**Recommendations:**

1. **Create Group Documentation File:**
   ```json
   {
     "_group_metadata": {
       "group_name": "Azure Logs Errors Overview",
       "purpose": "Monitor and alert on Azure-related errors in ABC cluster",
       "covered_errors": [
         "BatchErrorException",
         "OperationTimeoutException",
         "ResourceNotFound"
       ],
       "alert_recipients": "azure-oncall@company.com",
       "escalation": "If error rate > 10/min for > 5 min",
       "runbook": "https://wiki.company.com/runbooks/azure-errors"
     }
   }
   ```

2. **Add Error Type Classification:**
   - BatchError: Resource provisioning issues
   - OperationTimeout: Long-running operations stuck
   - Other: Transient or permission errors

3. **Add Recovery Actions:**
   - Document retry strategies
   - Link to remediation steps
   - Include common solutions per error type

---

### 4. **Logs Errors Overview Group**

**Recommendations:**

1. **Add Error Severity Levels:**
   ```json
   {
     "_widget_metadata": {
       "severity_levels": {
         "critical": "System unavailable or data loss risk",
         "high": "Service degraded, some users affected",
         "medium": "Feature partially broken, workaround exists",
         "low": "Non-blocking issue, informational"
       },
       "slos": {
         "critical": "must_alert",
         "high": "alert_if_sustained_5min",
         "medium": "log_only"
       }
     }
   }
   ```

2. **Create Error Correlation Heatmap:**
   - Show which errors tend to occur together
   - Help identify root causes
   - Link to related dashboards

---

### 5. **Management Overview Group**

**Recommendations:**

1. **Add Operational Metrics:**
   - Deployment frequency
   - Rollback rate
   - Configuration change tracking
   - Capacity planning metrics

2. **Include Health Checks:**
   ```json
   {
     "_health_indicators": {
       "system_health": {
         "query": "avg:system.uptime{*}",
         "threshold": "> 99.9%",
         "refresh": "1min"
       },
       "dependency_health": {
         "query": "avg:service.health_check{*}",
         "threshold": "all_passing",
         "refresh": "5min"
       }
     }
   }
   ```

---

### 6. **Pods Overview Group**

**Recommendations:**

1. **Add Pod Lifecycle Metrics:**
   - Pod restart count
   - Pending/CrashLoopBackOff status
   - Resource utilization trends
   - Image version tracking

2. **Include Scaling Events:**
   ```json
   {
     "_metrics": {
       "pod_count": "current_running_pods",
       "pod_desired": "target_pod_count",
       "scale_events": "hpa_triggered_events",
       "resources": {
         "cpu": "requested_vs_actual",
         "memory": "requested_vs_actual"
       }
     }
   }
   ```

---

### 7. **Response Time Distribution Group**

**Recommendations:**

1. **Add Percentile Breakdown:**
   ```json
   {
     "_percentiles": {
       "p50": "median response time",
       "p95": "95th percentile",
       "p99": "99th percentile",
       "p99.9": "99.9th percentile",
       "max": "maximum observed"
     },
     "_thresholds": {
       "p95": "< 500ms (SLO)",
       "p99": "< 1000ms (SLO)",
       "p99.9": "< 2000ms (info)"
     }
   }
   ```

2. **Add SLO Compliance Indicator:**
   - Show % of requests meeting SLO
   - Historical trend
   - Alert if SLO violated

3. **Include Breakdown by Service:**
   - Per-service response time
   - Identify bottlenecks
   - Compare improvements

---

### 8. **Shape Type Based Count of Jobs Group**

**Recommendations:**

1. **Add Job Type Classification:**
   ```json
   {
     "_job_types": {
       "cpu_intensive": "jobs that max out CPU",
       "memory_intensive": "jobs that require high memory",
       "io_intensive": "jobs with high disk/network I/O",
       "batch": "long-running batch jobs",
       "interactive": "quick interactive jobs"
     }
   }
   ```

2. **Add Cost Metrics:**
   - Estimated cost per job type
   - Total cost per shape type
   - Cost optimization opportunities

3. **Track Scheduling Efficiency:**
   - Queue depth per job type
   - Wait time before execution
   - Resource utilization

---

### 9. **Node Boot Time Per Shape Type Overview Group**

**Recommendations:**

1. **Add Boot Performance Targets:**
   ```json
   {
     "_targets": {
       "small_instance": "< 30 seconds",
       "medium_instance": "< 45 seconds",
       "large_instance": "< 60 seconds",
       "gpu_instance": "< 120 seconds"
     },
     "_historical": "trend over last 90 days"
   }
   ```

2. **Add Root Cause Analysis Tools:**
   - Slow image pull tracking
   - Kernel module load times
   - Cloud provider delays
   - Container runtime initialization

---

## General Recommendations for All Groups

### 1. **Add Schema Documentation**

Create `_schema.json` in root:
```json
{
  "widget_metadata": {
    "purpose": "string - Why this widget exists",
    "owner": "string - Team responsible",
    "metric_type": "enum - logs|metrics|traces|custom",
    "data_source": "string - logs_stream|metrics|etc",
    "query_explanation": "string - In-depth query explanation",
    "alert_rules": [
      {
        "condition": "string - When to alert",
        "severity": "enum - critical|high|medium|low",
        "recipient": "string - Email or channel"
      }
    ],
    "slos": {
      "target": "string - SLO target",
      "compliance": "number - Current compliance %"
    }
  }
}
```

### 2. **Add Version Control Comments**

```json
{
  "_version": "1.0.0",
  "_changelog": [
    {
      "version": "1.0.0",
      "date": "2025-10-29",
      "changes": "Initial dashboard creation",
      "author": "platform-team"
    }
  ]
}
```

### 3. **Add Related Dashboards Link**

```json
{
  "_related": [
    {
      "name": "Ambassador Routing Rules",
      "url": "/dashboard/abc/ambassador-routing",
      "reason": "Understand routing configuration"
    },
    {
      "name": "Cluster Health",
      "url": "/dashboard/xxx/cluster-health",
      "reason": "See overall cluster status"
    }
  ]
}
```

### 4. **Add Troubleshooting Guide**

```json
{
  "_troubleshooting": {
    "high_error_rate": {
      "possible_causes": [
        "Service unavailable",
        "Configuration error",
        "Resource exhaustion"
      ],
      "remediation_steps": [
        "Check service health",
        "Review recent deployments",
        "Check resource utilization"
      ],
      "runbook_link": "https://..."
    }
  }
}
```

### 5. **Add Metrics & KPIs Reference**

```json
{
  "_metrics": {
    "error_rate": {
      "query": "sum:errors{*} / sum:requests{*}",
      "unit": "%",
      "normal_range": "< 0.1%",
      "alert_threshold": "> 1%"
    },
    "response_time": {
      "query": "avg:latency{*}",
      "unit": "ms",
      "normal_range": "50-200ms",
      "alert_threshold": "> 500ms"
    }
  }
}
```

## File Organization Best Practices

### Current (Good):
```
abc_monitoring/
├── abc_monitoring.json                    ✓ Root dashboard
├── ambassador_overview/                   ✓ Logical grouping
│   ├── abc_monitoring_ambassador_*.json   ✓ Consistent naming
```

### Recommended (Better):
```
abc_monitoring/
├── _metadata.json                         NEW: Group metadata
├── _schema.json                           NEW: Schema definition
├── abc_monitoring.json                    ✓ Root dashboard
├── ambassador_overview/
│   ├── _group_metadata.json               NEW: Group-level metadata
│   ├── abc_monitoring_ambassador_*.json   ✓ Widget files
│   └── README.md                          NEW: Human-readable guide
├── azure_logs_errors_overview/
│   ├── _group_metadata.json
│   ├── abc_monitoring_azure_*.json
│   └── README.md
```

---

## Example: Updated File Structure

```
templates/
├── _metadata.json                          # Project-level metadata
├── _schema.json                            # JSON schema for all files
├── README.md                               # Setup & navigation guide
├── test_widget.json
└── abc_monitoring/
    ├── _metadata.json                      # ABC Monitoring metadata
    ├── _schema_overrides.json              # ABC-specific schema
    ├── README.md                           # ABC group documentation
    ├── abc_monitoring.json                 # Root dashboard
    ├── ambassador_overview/
    │   ├── _group_metadata.json
    │   ├── README.md
    │   ├── abc_monitoring_ambassador_error_logs_for_abc.json
    │   ├── abc_monitoring_ambassador_logs_for_abc.json
    │   ├── abc_monitoring_ambassador_non_200_201_response_code.json
    │   ├── abc_monitoring_ambassador_response_by_status_for_abc_non_200_201.json
    │   └── abc_monitoring_ambassador_response_by_status_for_abc.json
    └── [...other groups...]
```
