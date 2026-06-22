// MedQueue Analytics Script (PostHog & GA4)
// Placeholders for User to add real keys
const POSTHOG_API_KEY = "phc_AYsHG9zLKQCn5zuSNxaDavQxL5BSuUY3DFd2NBFa4ARQ";
const POSTHOG_HOST = "https://e.medqueue.me";
const POSTHOG_UI_HOST = "https://us.posthog.com";
const GA4_MEASUREMENT_ID = "G-Y86T417SGF";

// 1. Initialize PostHog
!function(t,e){var o,n,p,r;e.__SV||(window.posthog=e,e._i=[],e.init=function(i,s,a){function g(t,e){var o=e.split(".");2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}(p=t.createElement("script")).type="text/javascript",p.crossOrigin="anonymous",p.async=!0,p.src=s.api_host.replace(".i.posthog.com","-assets.i.posthog.com")+"/static/array.js",(r=t.getElementsByTagName("script")[0]).parentNode.insertBefore(p,r);var u=e;for(void 0!==a?u=e[a]=[]:a="posthog",u.people=u.people||[],u.toString=function(t){var e="posthog";return"posthog"!==a&&(e+="."+a),t||(e+=" (stub)"),e},u.people.toString=function(){return u.toString(1)+".people (stub)"},o="Rn Ln init Gn Jn Si Zn Yn Vn capture calculateEventProperties ns register register_once register_for_session unregister unregister_for_session ls getFeatureFlag getFeatureFlagPayload getFeatureFlagResult isFeatureEnabled reloadFeatureFlags updateFlags updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures on onFeatureFlags onSurveysLoaded onSessionId getSurveys getActiveMatchingSurveys renderSurvey displaySurvey cancelPendingSurvey canRenderSurvey canRenderSurveyAsync us identify setPersonProperties unsetPersonProperties group resetGroups setPersonPropertiesForFlags resetPersonPropertiesForFlags setGroupPropertiesForFlags resetGroupPropertiesForFlags reset setIdentity clearIdentity get_distinct_id getGroups get_session_id get_session_replay_url alias set_config startSessionRecording stopSessionRecording sessionRecordingStarted captureException addExceptionStep captureLog startExceptionAutocapture stopExceptionAutocapture loadToolbar get_property getSessionProperty ss ts createPersonProfile setInternalOrTestUser os Un ds opt_in_capturing opt_out_capturing has_opted_in_capturing has_opted_out_capturing get_explicit_consent_status is_capturing clear_opt_in_out_capturing Xn debug Ii mr getPageViewId captureTraceFeedback captureTraceMetric jn".split(" "),n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])},e.__SV=1)}(document,window.posthog||[]);
posthog.init(POSTHOG_API_KEY, {
    api_host: POSTHOG_HOST,
    ui_host: POSTHOG_UI_HOST,
    person_profiles: 'always',
    session_recording: {
        recordCrossOriginIframes: true
    },
    autocapture: true
});

// 2. Google Analytics (GA4) is now initialized directly in HTML <head>

// Helpers for triggering events from script.js
window.MedQueueAnalytics = {
    identifyUser: function(userId, email, name, plan) {
        posthog.identify(userId, { email: email, name: name, plan: plan });
        gtag('set', 'user_properties', { plan: plan });
        gtag('config', GA4_MEASUREMENT_ID, {
            'user_id': userId
        });
    },
    trackEvent: function(eventName, properties) {
        posthog.capture(eventName, properties);
        gtag('event', eventName, properties);
    }
};
