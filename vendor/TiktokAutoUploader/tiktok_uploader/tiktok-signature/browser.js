// Browser.js
const Signer = require("./index");

var url = process.argv[2];
var userAgent = process.argv[3];

(async function main() {
  let signer;
  try {
    // The URL to sign can be a TikTok API endpoint whose GET request never
    // reaches network-idle. Initialise on a local blank page and sign the
    // requested endpoint only after the bundled scripts are ready.
    signer = new Signer(null, userAgent);
    await signer.init();

    const sign = await signer.sign(url);
    const navigator = await signer.navigator();

    let output = JSON.stringify({
      status: "ok",
      data: {
        ...sign,
        navigator: navigator,
      },
    });
    console.log(output);
  } catch (err) {
    console.error(err);
    process.exitCode = 1;
  } finally {
    if (signer) {
      await signer.close().catch(() => {});
    }
  }
})();
