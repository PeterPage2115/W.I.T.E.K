/**
 * WITEK Extension — shared constants
 */

export const PAGE_TYPES = {
  REPORT: 'report',
  RALLY_POINT: 'rally_point',
  VILLAGE: 'village',
  UNKNOWN: 'unknown',
};

export const URL_PATTERNS = {
  REPORT: /berichte\.php\?.*id=(\d+)/,
  RALLY_POINT: /build\.php\?.*gid=16/,
  VILLAGE: /dorf1\.php/,
};

export const API_ENDPOINTS = {
  REPORT: '/api/ext/report',
  TROOPS: '/api/ext/troops',
  INCOMING: '/api/ext/incoming',
};

export const DEFAULTS = {
  SERVER_URL: '',
  TOKEN: '',
  ENABLED: false,
};
