(function () {
  "use strict";
  // ConsequenceMap desktop half.
  //
  // The dashboard tab (dashboard/dist/index.js) carries the three
  // surfaces. This half is the compact desktop panel: the forecast and
  // the comparison, in the place the user is already looking.
  const SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK || !window.__HERMES_PLUGINS__) return;

  const React = SDK.React;
  const h = React.createElement;

  function ConsequenceMapPanel() {
    return h("div", { className: "cm-panel-compact" },
      h("h3", null, "ConsequenceMap"),
      h("p", null, "See what happens before it happens.")
    );
  }

  if (window.__HERMES_PLUGINS__.registerSlot) {
    window.__HERMES_PLUGINS__.registerSlot(
      "consequence-map", "consequence-summary", ConsequenceMapPanel
    );
  }
})();
