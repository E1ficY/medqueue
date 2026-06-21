// MedQueue Analytics Script (PostHog & GA4)
// Placeholders for User to add real keys
const POSTHOG_API_KEY = "phc_AYsHG9zLKQCn5zuSNxaDavQxL5BSuUY3DFd2NBFa4ARQ";
const POSTHOG_HOST = "https://us.i.posthog.com";
const GA4_MEASUREMENT_ID = "G-F5TMGNGLTE";

// 1. Initialize PostHog
!function(t,e){var o,n,p,r;e.__SV||(window.posthog=e,e._i=[],e.init=function(i,s,a){function g(t,e){var o=e.split(".");2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}(p=t.createElement("script")).type="text/javascript",p.crossOrigin="anonymous",p.async=!0,p.src=s.api_host.replace(".i.posthog.com","-assets.i.posthog.com")+"/static/array.js",(r=t.getElementsByTagName("script")[0]).parentNode.insertBefore(p,r);var u=e;for(void 0!==a?u=e[a]=[]:a="posthog",u.people=u.people||[],u.toString=function(t){var e="posthog";return"posthog"!==a&&(e+="."+a),t||(e+=" (stub)"),e},u.people.toString=function(){return u.toString(1)+".people (stub)"},o="init capture register register_once register_for_session unregister unregister_for_session getFeatureFlag getFeatureFlagPayload isFeatureEnabled reloadFeatureFlags updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures on onFeatureFlags onSessionId getSurveys getActiveMatchingSurveys renderSurvey canRenderSurvey getNextSurveyStep identify setPersonProperties group reset groups setPersonPropertiesForFlags resetPersonPropertiesForFlags setGroupPropertiesForFlags resetGroupPropertiesForFlags resetGroups set_config startSessionRecording stopSessionRecording sessionRecordingStarted captureException loadToolbar get_distinct_id getGroups get_session_id get_session_replay_url alias set_config".split(" "),n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])},e.__SV=1)}(document,window.posthog||[]);
posthog.init(POSTHOG_API_KEY, {
    api_host: POSTHOG_HOST,
    person_profiles: 'always',
    session_recording: {
        recordCrossOriginIframes: true
    },
    autocapture: true
});

// 2. Initialize Google Analytics (GA4)
const gaScript = document.createElement('script');
gaScript.async = true;
gaScript.src = `https://www.googletagmanager.com/gtag/js?id=${GA4_MEASUREMENT_ID}`;
document.head.appendChild(gaScript);

window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag('js', new Date());
gtag('config', GA4_MEASUREMENT_ID);

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
