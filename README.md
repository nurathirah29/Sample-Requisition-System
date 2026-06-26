# Sample Requisition System

A Flask-based web application for managing sample requests between two internal teams — ERJ (requesters) and ERM (fulfillers). ERJ submits sample requests with item details, and ERM reviews and provides possible delivery dates. The system includes in-app notifications, activity logging, and email alerts at each workflow stage.

---

## Features

- **Two-role workflow** — ERJ submits and closes requests; ERM reviews and updates delivery dates
- **Request lifecycle** — Open → Completed → Closed
- **Sample items** — Each request supports multiple sample lines (name, quantity, packing option)
- **Activity log** — Full audit trail per request (who did what and when)
- **Email notifications** — Alerts sent to ERM on new/edited requests; alerts sent to ERJ on status updates
- **Search & filter** — Filter by status, search by request number, customer, model, or requester name
- **Pagination** — 15 records per page across both dashboards
- **Detail modal** — View full request detail, sample items, and activity log via JSON API

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask |
| Database | MySQL (`mysql-connector-python`) |
| Frontend | HTML, Jinja2 templates |
| Email | SMTP via `smtplib` |

---

## Database Schema

| Table | Description |
|---|---|
| `users` | User accounts with `id`, `name`, `email`, `role` (`ERJ` or `ERM`) |
| `sample_requests` | Request header — customer, model, shipping info, status, dates |
| `sample_items` | Line items per request — sample name, quantity, packing option |
| `notifications` | In-app notification records per user |
| `activity_logs` | Audit trail — action, performed by, remarks, timestamp |

### Key fields in `sample_requests`

| Field | Description |
|---|---|
| `request_no` | Auto-generated ID, format: `SR-YYMMDD-NNN` |
| `requester_id` | FK to `users` (ERJ) |
| `assigned_to` | FK to `users` (ERM who last updated) |
| `status` | `Open`, `Completed`, or `Closed` |
| `request_delivery_date` | ERJ's requested delivery date |
| `possible_delivery_date` | ERM's estimated delivery date (triggers Completed) |

---

## User Roles

| Role | Access |
|---|---|
| ERJ | Submit new requests, edit open/completed requests, close completed requests |
| ERM | View all requests, set possible delivery date, update status |

Login is email-based — no password. The role is determined by the `role` field in the `users` table.

---

## Request Workflow

```
ERJ submits request
        ↓
  Status: Open
        ↓   ← All ERMs notified by email
ERM sets possible delivery date
        ↓
  Status: Completed
        ↓   ← ERJ notified by email
ERJ reviews and closes
        ↓
  Status: Closed
```

- ERJ can **edit** a request when status is `Open` or `Completed`
- ERJ can **close** a request only when status is `Completed`
- ERM can update any `Open` or `Completed` request
- Setting a `possible_delivery_date` automatically moves status to `Completed`

---

## Request ID Format

Request numbers are auto-generated on submission:

```
SR-YYMMDD-NNN
```

Example: `SR-260626-001` — first request submitted on 26 June 2026.

The sequence resets daily based on `COUNT(*)` of requests created that day.

---

## Key Routes

| Method | Route | Role | Description |
|---|---|---|---|
| GET/POST | `/` | Public | Login page |
| GET | `/logout` | Any | Clear session and redirect to login |
| GET | `/erj` | ERJ | ERJ dashboard with filters and pagination |
| POST | `/submit` | ERJ | Submit a new sample request |
| POST | `/erj/edit/<id>` | ERJ | Edit an existing Open or Completed request |
| POST | `/erj/close/<id>` | ERJ | Close a Completed request |
| GET | `/erm` | ERM | ERM dashboard with filters and pagination |
| POST | `/erm/update/<id>` | ERM | Set delivery date / update status |
| GET | `/detail/<id>` | Any | Returns full request detail as JSON (for modal) |
| GET | `/notifications` | Any | Notification inbox (marks all as read) |
| GET | `/api/unread` | Any | Returns unread notification count as JSON |

---

## Email Notifications

| Trigger | Recipients | Content |
|---|---|---|
| New request submitted | All ERMs | Request details + sample items table |
| Request edited by ERJ | All ERMs | Request number, customer, model |
| ERM sets delivery date | ERJ (requester) | New status + possible delivery date + remarks |

Emails are sent silently — failures are logged to console but do not interrupt the request flow.

---

## Author

Nur Athirah
