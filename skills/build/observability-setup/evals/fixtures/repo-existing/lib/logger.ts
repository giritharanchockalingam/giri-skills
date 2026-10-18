// A hand-rolled logger that predates the starter kit; must not be overwritten.
export const logger = { info: (msg: string) => process.stdout.write(msg + "\n") };
