import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.agenthub.mobile",
  appName: "AgentHub Mobile",
  webDir: "dist",
  bundledWebRuntime: false,
  server: {
    androidScheme: "http",
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 1200,
      backgroundColor: "#23433d",
      showSpinner: false,
    },
  },
};

export default config;
