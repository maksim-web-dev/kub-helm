import http from 'k6/http';
import { sleep, check } from 'k6';

export const options = {
  scenarios: {
    load: {
      executor: 'constant-arrival-rate',
      rate: 1000,
      timeUnit: '1s',
      duration: '2m',
      preAllocatedVUs: 500,
      maxVUs: 1000,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500'],
  },
};

export default function () {
  const res = http.get('http://localhost/');
  check(res, {
    'status is 200': (r) => r.status === 200,
  });
}