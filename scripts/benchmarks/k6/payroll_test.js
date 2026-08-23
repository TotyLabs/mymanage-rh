import http from 'k6/http';
import { sleep, check } from 'k6';

export let options = {
  vus: 10,
  duration: '1m',
};

export default function () {
  let res = http.get('http://localhost:8000/');
  check(res, { 'status 200': (r) => r.status === 200 });
  sleep(1);
}
