const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const TIME_PATTERN = /^(?:[01]\d|2[0-3]):[0-5]\d$/;

function zonedParts(date, timeZone) {
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  });
  return Object.fromEntries(
    formatter.formatToParts(date)
      .filter((part) => part.type !== 'literal')
      .map((part) => [part.type, part.value]),
  );
}

export function assertDate(value) {
  if (!DATE_PATTERN.test(value)) throw new Error(`Invalid date: ${value}`);
  return value;
}

export function assertTime(value) {
  if (!TIME_PATTERN.test(value)) throw new Error(`Invalid time: ${value}`);
  return value;
}

export function dateInTimeZone(now = new Date(), timeZone = 'Europe/Paris') {
  const parts = zonedParts(now, timeZone);
  return `${parts.year}-${parts.month}-${parts.day}`;
}

export function minutesInTimeZone(now = new Date(), timeZone = 'Europe/Paris') {
  const parts = zonedParts(now, timeZone);
  return Number(parts.hour) * 60 + Number(parts.minute);
}

export function timeToMinutes(value) {
  const [hour, minute] = assertTime(value).split(':').map(Number);
  return hour * 60 + minute;
}

export function isTimeDue(value, now = new Date(), timeZone = 'Europe/Paris') {
  return minutesInTimeZone(now, timeZone) >= timeToMinutes(value);
}

export function addDays(date, amount) {
  assertDate(date);
  const instant = new Date(`${date}T12:00:00.000Z`);
  instant.setUTCDate(instant.getUTCDate() + amount);
  return instant.toISOString().slice(0, 10);
}

export function dayOrdinal(date) {
  assertDate(date);
  return Math.floor(Date.parse(`${date}T00:00:00.000Z`) / 86_400_000);
}
