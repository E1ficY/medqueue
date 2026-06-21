# MedQueue Analytics & KPIs (Week 5)

## 1. Core Implementation
This document outlines the final analytics integration for the MedQueue startup (Sprint 5). We've successfully integrated both PostHog and Google Analytics 4 (GA4).

### Tools Used
- **PostHog**: For product analytics, feature flags, and detailed event tracking (Acquisition, Activation, Revenue, Retention).
- **Google Analytics 4 (GA4)**: For e-commerce tracking (`begin_checkout`, `purchase`, `sign_up`) and high-level marketing acquisition metrics.

## 2. Event Taxonomy

### Acquisition
- **`user signed up`**: Fired when a user successfully registers via Email/Password or OAuth.
- **`user connected google oauth`**: Fired when a user logs in via Google for the first time.

### Activation
- **`user completed profile`**: Fired when a user uploads an avatar.
- **`first product viewed`**: Fired the first time a user views a doctor's profile.
- **`first search performed`**: Fired the first time a user uses the search bar.

### Revenue (E-Commerce)
- **`checkout started`** (PostHog) & **`begin_checkout`** (GA4): Fired when a user initiates the payment process.
- **`payment failed`**: Fired when a payment is declined.
- **`payment completed`** (PostHog) & **`purchase`** (GA4): Fired upon successful subscription payment.
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

## 7. Frontend Integration
A global analytics script (`startup/js/analytics.js`) has been injected into all 13 HTML files. The script automatically handles:
- Initializing `posthog` (with autocapture and session recording)
- Initializing `gtag` (with user_id tracking)
- Providing a wrapper object (`window.MedQueueAnalytics`) to simplify tracking from `script.js`.
- Automatic user identification across sessions (`identifyUser`) using `localStorage` auth data.
