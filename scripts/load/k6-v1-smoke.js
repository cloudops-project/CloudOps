import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  vus: Number(__ENV.K6_VUS || 5),
  duration: __ENV.K6_DURATION || "30s",
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<1500"],
  },
};

const baseUrl = __ENV.CLOUDOPS_BASE_URL;
if (!baseUrl || !baseUrl.startsWith("http")) {
  throw new Error("CLOUDOPS_BASE_URL is required");
}

export default function () {
  const live = http.get(`${baseUrl}/health`);
  check(live, { "liveness returns 200": (response) => response.status === 200 });

  const ready = http.get(`${baseUrl}/ready`);
  check(ready, { "readiness returns 200": (response) => response.status === 200 });
  sleep(1);
}
