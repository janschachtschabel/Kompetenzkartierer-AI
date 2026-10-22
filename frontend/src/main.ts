import { createApp } from "vue";
// Self-hosted rather than pulled from a font CDN at runtime: hotlinking one
// sends the IP of every visitor to the provider, which German courts have held
// to breach the GDPR. Vite copies the woff2 into the bundle, so the container
// serves them from its own origin. The variable cut carries every weight in one
// file, and each @font-face names its unicode range, so a German page fetches
// the latin subset and nothing else.
import "@fontsource-variable/roboto/wght.css";
import "@fontsource-variable/roboto-mono/wght.css";

import App from "./App.vue";
import { t } from "./i18n/de";
import "./style.css";

document.title = t("app.title");
createApp(App).mount("#app");
