# Templates Best Practices - Quick Reference Guide

**Purpose:** Fast reference for implementing best practices in JSON templates

---

## At-a-Glance Summary

| Group | Current State | Recommendation | Priority | Effort |
|-------|---------------|-----------------|----------|--------|
| **Root** | No metadata | Add ownership, SLOs, version | High | Low |
| **Ambassador** | Minimal docs | Add query explanation, runbook | High | Medium |
| **Azure Logs** | Inconsistent | Create group metadata | High | Medium |
| **Logs Errors** | Basic structure | Add error classification | Medium | Low |
| **Management** | Minimal structure | Add health indicators | Medium | Medium |
| **Pods** | Basic tracking | Add lifecycle alerts | Medium | Medium |
| **Response Time** | Time-based only | Add SLO alignment | High | Low |
| **Shape Types** | Metrics missing | Add cost & optimization | Low | Medium |
| **Boot Time** | Performance only | Add baseline tracking | Low | Low |

---

## Quick Wins (Easy, High Impact)

### 1. Add Version to Root
```json
{
  "title": "ABC_Monitoring",
  "_metadata": {
    "version": "1.0.0",
    "owner": "platform-team"
  }
}
```

### 2. Add Owner to Each Group
```json
{
  "_widget_metadata": {
    "owner": "platform-team",
    "on_call": "email@company.com"
  }
}
```

### 3. Add SLO Targets
```json
{
  "_widget_metadata": {
    "slos": {
      "target": "99.9%",
      "alert_threshold": "< 99%"
    }
  }
}
```

### 4. Add Links
```json
{
  "_metadata": {
    "runbook": "https://wiki.company.com/runbooks/xxx",
    "documentation": "https://wiki.company.com/dashboards/xxx"
  }
}
```

## Metadata Checklist

### For Root Dashboard

```
☐ version (semantic: 1.0.0)
☐ owner (team or individual)
☐ on_call_team (email)
☐ documentation URL
☐ runbook URL
☐ slack_channel (#alerts)
☐ tags (searchable)
☐ slos (business metrics)
☐ template_variables (with defaults)
☐ dependencies (what's needed)
```

### For Each Group

```
☐ purpose statement
☐ owner
☐ on_call contact
☐ covered items/metrics
☐ slos per metric
☐ runbook link
☐ alert recipients
☐ escalation path
☐ related dashboards
☐ troubleshooting guide
```

### For Each Widget

```
☐ purpose
☐ owner
☐ metric_type (logs|metrics|traces)
☐ data_source
☐ query_explanation
☐ alert_rules
☐ slos
☐ refresh_rate
☐ retention_period
☐ runbook
☐ related_resources
```

---

## File Templates

### Group Metadata Template

```json
{
  "_group_metadata": {
    "name": "GROUP_NAME",
    "purpose": "Brief description of what this group monitors",
    "owner": "team-name",
    "on_call": "email@company.com",
    "scope": "What systems/services does this cover?",
    "slos": {
      "metric_name": {
        "target": "acceptable value",
        "alert_threshold": "alert when exceeded"
      }
    },
    "runbook": "https://wiki.company.com/runbooks/GROUP_NAME",
    "documentation": "https://wiki.company.com/dashboards/GROUP_NAME",
    "alert_recipients": ["email@company.com"],
    "escalation": {
      "level_1": "First responder",
      "level_2": "If not resolved in X time",
      "level_3": "Escalation path"
    },
    "related_dashboards": [
      {
        "name": "Related Dashboard",
        "description": "Why it's related"
      }
    ]
  }
}
```

### Widget Metadata Template

```json
{
  "_widget_metadata": {
    "purpose": "What does this widget show?",
    "owner": "team-name",
    "metric_type": "logs|metrics|traces|custom",
    "data_source": "where data comes from",
    "alert_recipients": ["email@company.com"],
    "slos": {
      "target": "expected range",
      "alert_threshold": "when to alert"
    },
    "query_explanation": "Detailed explanation of the query logic",
    "refresh_rate": "30s",
    "retention": "7 days",
    "runbook": "https://wiki.company.com/runbooks/WIDGET",
    "troubleshooting": {
      "common_issue": {
        "possible_causes": ["cause1", "cause2"],
        "remediation_steps": ["step1", "step2"]
      }
    }
  }
}
```

---

## Common SLO Targets

### For Error Tracking
```
target: "< 0.1% error rate"
alert: "> 1% for 5 minutes"
```

### For Response Times
```
target: "< 500ms p95"
alert: "> 1000ms p99"
```

### For Availability
```
target: "> 99.9%"
alert: "< 99% for 15 minutes"
```

### For System Health
```
target: "all checks passing"
alert: "any check failing for > 1 minute"
```

---

## Documentation Links Template

```json
{
  "_metadata": {
    "documentation": "https://wiki.company.com/dashboards/abc-monitoring",
    "runbook": "https://wiki.company.com/runbooks/abc-monitoring",
    "slack_channel": "#abc-alerts",
    "team_page": "https://wiki.company.com/teams/platform",
    "related_links": [
      {
        "name": "ABC Integration Guide",
        "url": "https://wiki.company.com/abc-integration"
      },
      {
        "name": "Alert Policy",
        "url": "https://wiki.company.com/alert-policy"
      }
    ]
  }
}
```

---

## Common Mistakes to Avoid

❌ **Don't:**
- Leave metadata empty strings
- Use outdated links
- Mix naming conventions
- Have multiple owners without clear role
- Add too many nested levels

✅ **Do:**
- Keep metadata concise but complete
- Update links when documentation changes
- Stay consistent with naming
- Define clear ownership
- Use standard field names
