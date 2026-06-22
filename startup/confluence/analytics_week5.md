# MedQueue Analytics & KPIs (Week 5)

## 1. Core Implementation
This document outlines the final analytics integration for the MedQueue startup (Sprint 5). We've successfully integrated both PostHog and Cloudflare Web Analytics (replacing Google Analytics 4).

### Tools Used
- **PostHog**: For product analytics, feature flags, detailed event tracking (Acquisition, Activation, Revenue, Retention), and Session Replays.
- **Cloudflare Web Analytics**: For privacy-first, lightweight tracking of page views and high-level marketing acquisition metrics directly from the edge network. We opted for this over GA4 to ensure maximum site performance, bypass ad-blockers, and avoid complex Content Security Policy (CSP) conflicts.

## 2. Event Taxonomy (PostHog)

### Acquisition
- **`user signed up`**: Fired when a user successfully registers via Email/Password or OAuth.
- **`user connected google oauth`**: Fired when a user logs in via Google for the first time.

### Activation
- **`user completed profile`**: Fired when a user uploads an avatar.
- **`first product viewed`**: Fired the first time a user views a doctor's profile.
- **`first search performed`**: Fired the first time a user uses the search bar.

### Revenue (E-Commerce)
- **`checkout started`**: Fired when a user initiates the payment process.
- **`payment failed`**: Fired when a payment is declined.
- **`payment completed`**: Fired upon successful subscription payment.
- **`subscription activated`**: Fired alongside `payment completed` for tracking active subscription periods.

### Retention
- **`user logged in`**: Fired on each successful login.
- **`subscription cancelled`**: Fired when a user cancels their subscription.

## 3. KPIs & Admin Dashboard
The Admin Dashboard (`/api/admin/stats/`) has been updated to automatically calculate the following KPIs:

- **Conversion Rate (`conversion_rate`)**: Percentage of total users who have an active Plus subscription.
  - *Formula: (Active Plus Subs / Total Users) * 100*
- **Monthly Recurring Revenue (`mrr`)**: The total predictable revenue from active subscriptions.
  - *Formula: Active Plus Subs * 2990 ₸*
- **Churn Rate (`churn_rate`)**: The percentage of paid users who have cancelled their subscription.
  - *Formula: (Cancelled Subs / Total Ever Paid Subs) * 100*

These metrics are now prominently displayed on the frontend Admin Panel using custom CSS cards.

## 4. Feature Flags
We've implemented feature flags using PostHog to safely roll out new features.
- **`new-dashboard`**: Used in `/api/admin/stats/` to determine which dashboard version (`v1` or `v2`) to serve to the user. This allows us to test the new dashboard layout on a subset of users before a full release.

## 5. Session Recording
PostHog Session Recording (Replay) is enabled in `analytics.js` (`session_recording: { recordCrossOriginIframes: true }`). 
- This allows us to watch real user sessions to identify UX friction points (e.g., rage clicks, dead clicks, and checkout abandonment).

## 6. Conversion Funnel
The primary conversion funnel to be visualized in PostHog UI:
1. `user signed up` (Acquisition)
2. `user completed profile` (Activation)
3. `checkout started` (Revenue intent)
4. `payment completed` (Revenue realization)

## 7. Troubleshooting & Architectural Decisions

| Error/Issue | Root Cause | Solution Implemented |
| :--- | :--- | :--- |
| **Site Layout Breaking / Blank Page (Error 502/521)** | Google Tag Manager (GTM) injected `unsafe-inline` scripts and iframes that clashed with our strict Nginx and Django CSP, causing the browser to block critical site rendering. | Removed GTM/GA4 entirely. Migrated to **Cloudflare Web Analytics**, which operates at the edge level and requires zero code changes or CSP compromises. |
| **Events not appearing in PostHog ("where am i?")** | The site was communicating with the PostHog Custom Domain (`e.medqueue.me`), but Nginx and Django CSP blocked the outgoing requests to this domain. | Added `https://e.medqueue.me` to the `connect-src` and `script-src` whitelist in both Nginx and Django middleware CSP. |
| **Browser caching old analytics scripts** | When applying CSP and custom domain fixes, Cloudflare and local browsers served a cached `analytics.js` (up to 30 days) that still pointed to the wrong API endpoints. | Appended a cache buster query parameter (`?v=2026-06-22-ph`) to the script source in all 13 HTML files to force browsers to fetch the fresh code. |
| **PostHog SDK "Critical Outdated" Alert** | The backend Docker container was built with `posthog>=3.6.0`, which resolved to an outdated `7.13.1` version, falling behind the required `7.19.2`. | Updated `requirements.txt` to use a compatible release pin (`posthog~=7.19`), rebuilt the Docker container, and ensured both the backend and celery worker received the update. |
