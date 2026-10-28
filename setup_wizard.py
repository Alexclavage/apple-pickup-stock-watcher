"""Local-only configuration wizard for Apple Stock Watcher.

Launch with: python setup_wizard.py
The wizard binds to loopback, is not part of the public monitoring server,
and never reads or writes Discord webhook credentials.
"""
import argparse
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
import tempfile

from flask import Flask, abort, jsonify, render_template_string, request
from monitoring_areas import MAX_MONITORING_AREAS, legacy_areas, validate_monitoring_areas


ROOT = Path(__file__).resolve().parent
PRODUCT_ID = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,39}$")
SKU = re.compile(r"^[a-zA-Z0-9/_-]{3,32}$")
STORE_ID = re.compile(r"^[a-zA-Z0-9_-]{2,20}$")
AREA_NAME = re.compile(r"^[a-zA-Z0-9 _-]{1,32}$")
US_ZIP = re.compile(r"^[0-9]{5}$")
STATE = re.compile(r"^[A-Z]{2}$")


class InvalidConfig(ValueError):
    pass


def _string(value, name, limit=120, empty=False):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise InvalidConfig(f"{name} must be a {'possibly empty ' if empty else ''}string (max {limit} characters)")
    return value.strip()


def _string_list(value, name, regex=None, max_items=100):
    if not isinstance(value, list) or len(value) > max_items:
        raise InvalidConfig(f"{name} must be an array with at most {max_items} elements")
    values = []
    for entry in value:
        entry = _string(entry, name, limit=40)
        if regex and not regex.fullmatch(entry):
            raise InvalidConfig(f"{name} contains an invalid value: {entry[:24]}")
        if entry in values:
            raise InvalidConfig(f"{name} contains duplicates")
        values.append(entry)
    return values


def validate_config(cfg):
    """Validate wizard-owned fields before overwriting any local file."""
    if not isinstance(cfg, dict):
        raise InvalidConfig("Configuration must be an object")

    products = cfg.get("products")
    if not isinstance(products, dict) or not 1 <= len(products) <= 25:
        raise InvalidConfig("Add between 1 and 25 products")
    result = {}
    for product_id, item in products.items():
        if not isinstance(product_id, str) or not PRODUCT_ID.fullmatch(product_id):
            raise InvalidConfig("Product IDs must start with a letter and contain letters, digits, underscores or hyphens")
        if not isinstance(item, dict):
            raise InvalidConfig(f"Product {product_id} must be an object")
        market = item.get("market")
        if market not in ("US", "CA"):
            raise InvalidConfig(f"Invalid country for {product_id}")
        currency = item.get("currency")
        if currency != ("USD" if market == "US" else "CAD"):
            raise InvalidConfig(f"Invalid currency for {product_id}")
        sku = _string(item.get("part"), f"SKU for {product_id}", 32)
        if not SKU.fullmatch(sku):
            raise InvalidConfig(f"Invalid SKU for {product_id}")
        price = item.get("price")
        if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or not 0 <= price <= 100000:
            raise InvalidConfig(f"Price for {product_id} must be a valid nonnegative number")
        result[product_id] = {
            "market": market,
            "name": _string(item.get("name"), f"Name for {product_id}", 100),
            "part": sku,
            "price": price,
            "currency": currency,
        }

    zips = cfg.get("search_zips", {})
    if not isinstance(zips, dict) or len(zips) > 20:
        raise InvalidConfig("US search regions must be an object with at most 20 entries")
    valid_zips = {}
    for name, postal in zips.items():
        if not isinstance(name, str) or not AREA_NAME.fullmatch(name):
            raise InvalidConfig("US region names can contain only letters, digits, spaces, hyphens and underscores")
        if not isinstance(postal, str) or not US_ZIP.fullmatch(postal):
            raise InvalidConfig(f"US ZIP for {name} must contain exactly 5 digits")
        valid_zips[name] = postal
    if "monitoring_areas" not in cfg and any(item["market"] == "US" for item in result.values()) and not valid_zips:
        raise InvalidConfig("Add a US ZIP search region for US products")

    states = _string_list(cfg.get("allowed_states", []), "Allowed US states", STATE, 51)
    us_store = _string(cfg.get("us_priority_store", ""), "Priority US store", 20, empty=True)
    ca_store = _string(cfg.get("ca_target_store", ""), "Target Canadian store", 20, empty=True)
    for title, value in (("Priority US store", us_store), ("Target Canadian store", ca_store)):
        if value and not STORE_ID.fullmatch(value):
            raise InvalidConfig(f"{title} has invalid characters")

    ca_postal = _string(cfg.get("ca_location", ""), "Canadian location", 24, empty=True)
    if "monitoring_areas" not in cfg and any(item["market"] == "CA" for item in result.values()) and not ca_postal:
        raise InvalidConfig("Enter a Canadian location when monitoring Canadian products")
    tax = cfg.get("ca_tax_rate", 0.13)
    if isinstance(tax, bool) or not isinstance(tax, (int, float)) or not math.isfinite(tax) or not 0 <= tax <= 1:
        raise InvalidConfig("Canadian tax estimate must be between 0 and 1")

    output = {
        "products": result,
        "search_zips": valid_zips,
        "allowed_states": states,
        "us_priority_store": us_store,
        "ca_location": ca_postal,
        "ca_target_store": ca_store,
        "ca_tax_rate": tax,
    }
    if "monitoring_areas" in cfg:
        try:
            output["monitoring_areas"] = validate_monitoring_areas(cfg["monitoring_areas"], result)
        except ValueError as exc:
            raise InvalidConfig(str(exc)) from exc
    for key, regex in (("alert_store_ids", STORE_ID), ("alert_product_ids", PRODUCT_ID)):
        if key in cfg:
            values = _string_list(cfg[key], key, regex)
            if key == "alert_product_ids" and not set(values).issubset(result):
                raise InvalidConfig("Alert products must refer to configured product IDs")
            output[key] = values
    return output


WIZARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Apple Watcher — Local Setup</title>
<style>
:root{color-scheme:dark;--bg:#000;--panel:#101216;--border:#30343d;--text:#f8f8fa;--muted:#a1a8b5;--blue:#2997ff;--green:#30d985;--red:#ff6575}
*{box-sizing:border-box}body{font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:var(--bg);color:var(--text);margin:0;padding:30px 20px}
main{max-width:1050px;margin:auto}header{margin-bottom:25px}h1{font-size:clamp(27px,5vw,40px);margin:0 0 8px;letter-spacing:-.04em}h2{font-size:21px;letter-spacing:-.025em;margin:0 0 7px}p{margin:0 0 15px;color:var(--muted)}
section{background:var(--panel);border:1px solid var(--border);border-radius:21px;padding:22px;margin-bottom:18px}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:11px}.full{grid-column:1/-1}
label{display:block;color:var(--muted);font-size:13px;margin-bottom:5px}input,select{width:100%;border:1px solid var(--border);border-radius:10px;background:#191d25;color:var(--text);font:inherit;padding:10px 11px;outline:none;min-width:0}
input:focus,select:focus{border-color:var(--blue)}button{font:inherit;cursor:pointer;border:1px solid var(--border);background:#222833;color:var(--text);padding:10px 16px;border-radius:12px}
button.primary{background:var(--blue);border-color:var(--blue);color:#fff;font-weight:650}button.remove{color:#ff9fa6;border-color:#58333c;background:#28191d}button:disabled{opacity:.6;cursor:wait}
.toolbar{display:flex;gap:12px;justify-content:space-between;align-items:center;flex-wrap:wrap;margin-bottom:13px}
.entry{background:#171a20;padding:16px;border:1px solid var(--border);border-radius:15px;margin-bottom:10px}
.entry-top{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:12px}
.entry-top strong{font-size:13px}small{font-size:12px;color:var(--muted)}.info{background:#102218;border:1px solid #225238;padding:11px 15px;border-radius:12px;color:#d6f7df;margin-bottom:16px}
.actions{display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin:20px 0}#message{min-height:22px;color:var(--muted)}.toggle{display:flex;align-items:center;gap:8px;color:var(--text);margin:7px 0 12px}.toggle input{width:auto}
@media(max-width:750px){.grid,.fields{grid-template-columns:1fr}.full{grid-column:1}section{padding:16px}body{padding:20px 12px}}
.area-warning{border:1px solid #b18533;background:#30230f;color:#ffd997;padding:14px 16px;border-radius:14px;margin-top:12px}.area-warning p{color:#f0d3a6;margin:4px 0 0}.area-warning[hidden]{display:none}
</style>
</head><body><main>
<header><small>APPLE STOCK WATCHER / LOCAL SETUP</small><h1>Make it yours.</h1><p>Configure products, stores, prices and alerts without editing JSON.</p></header>
<div class="info">🔒 This wizard runs only on your computer (127.0.0.1). No webhook secrets are displayed or saved here.</div>
<section><div class="toolbar"><div><h2>1. Products</h2><p>Use Apple's region-specific SKU. The example values are illustrative, not an automatically updated product catalogue.</p></div><button id="addProduct" type="button">+ Add product</button></div><div id="products"></div></section>
<section>
<div class="toolbar"><div><h2>2. Monitoring areas</h2><p>Select a country and postal code or city for each area. US currently requires a five-digit ZIP; Canada also accepts a city, but postal codes are recommended. Countries beyond US/Canada will be added as validated.</p></div>
<button id="addRegion" type="button">+ Add area</button></div>
<div id="regions"></div>
<div class="info" id="areaEstimate" role="status" aria-live="polite">Estimated requests: 1 per area per scan.</div>
<div id="areaWarning" class="area-warning" hidden><strong>⚠ Multiple monitoring areas</strong><p>More areas mean more Apple requests. Monitoring may become slower, return partial results, or be temporarily interrupted by rate limits. The app spaces requests, stops a scan when Apple throttles it, and never reports missed checks as confirmed out-of-stock.</p></div>
</section>
<div class="grid">
<section><h2>3. United States</h2><p>Advanced: filter which US states may appear in monitoring results.</p>
<label for="states">Allowed US states (comma-separated, blank = all)</label><input id="states" placeholder="DE, NY, NJ, PA">
<label for="priority" style="margin-top:12px">Priority US store ID (optional)</label><input id="priority" placeholder="R102"></section>
<section><h2>Canadian tax estimate</h2><p>Only a configurable estimate, not a nationwide tax rate.</p>
<label for="caTax">Estimated sales tax (%)</label><input id="caTax" type="number" min="0" max="100" step=".01" placeholder="13"></section>
</div>
<section><h2>4. Discord alert filters</h2><p>These filters affect notifications, not what appears on the dashboard. Configure your Discord webhook separately in your private .env file.</p>
<div class="grid"><div>
<label class="toggle"><input id="allStores" type="checkbox" checked> Alert for all stores</label>
<label for="alertStores">Store IDs when filtering (comma separated)</label><input id="alertStores" placeholder="R102, R121" disabled>
</div><div>
<label class="toggle"><input id="allProducts" type="checkbox" checked> Alert for all configured products</label>
<label for="alertProducts">Product IDs when filtering (comma separated)</label><input id="alertProducts" placeholder="us_pro_512" disabled>
</div></div><small>Uncheck and leave a field empty to disable notifications for that dimension.</small>
</section>
<div class="actions"><button class="primary" type="button" id="save">Save private configuration</button><span id="message" role="status" aria-live="polite"></span></div>
<p>Saved to <code>config.json</code> next to the watcher. Restart the watcher to apply changes. This wizard does not start monitoring or send notifications.</p>
</main>
<template id="productTemplate"><article class="entry product-entry"><div class="entry-top"><strong>Product</strong><button type="button" class="remove">Remove</button></div><div class="fields">
<div><label>Product ID</label><input class="pid" placeholder="us_pro_512" maxlength="40"></div>
<div><label>Market</label><select class="market"><option value="US">United States</option><option value="CA">Canada</option></select></div>
<div class="full"><label>Display name</label><input class="pname" placeholder="iPhone 18 Pro 512GB Silver" maxlength="100"></div>
<div><label>Apple SKU</label><input class="sku" placeholder="MJQ84LL/A" maxlength="32"></div>
<div><label>Price before tax</label><input class="price" type="number" min="0" max="100000" step=".01"></div>
</div></article></template>
<template id="regionTemplate"><article class="entry region-entry"><div class="entry-top"><strong>Monitoring area</strong><button type="button" class="remove">Remove</button></div><div class="fields">
<div><label>Area ID</label><input class="areaId" placeholder="us_delaware" maxlength="32"></div>
<div><label>Country</label><select class="country"><option value="US">United States</option><option value="CA">Canada</option></select></div>
<div><label>ZIP / postal code or city</label><input class="location" placeholder="19702 or M5B 2H1" maxlength="64"></div>
<div><label>Apple Store IDs (optional; blank = all returned)</label><input class="areaStores" placeholder="R102, R121"></div>
</div></article></template>
<script>
const TOKEN = {{ token | tojson }};
let original = {};
const el = id => document.getElementById(id);
const splitIds = value => value.split(",").map(s=>s.trim()).filter(Boolean);
function productRow(id, p) {
  const root=el("productTemplate").content.firstElementChild.cloneNode(true);
  root.querySelector(".pid").value=id||"";
  root.querySelector(".market").value=p.market||"US";
  root.querySelector(".pname").value=p.name||"";
  root.querySelector(".sku").value=p.part||"";
  root.querySelector(".price").value=p.price??"";
  root.querySelector(".remove").addEventListener("click",()=>root.remove());
  el("products").appendChild(root);
}
function regionRow(area){
  const root=el("regionTemplate").content.firstElementChild.cloneNode(true);
  root.querySelector(".areaId").value=area.id||"";
  root.querySelector(".country").value=area.market||"US";
  root.querySelector(".location").value=area.location||"";
  root.querySelector(".areaStores").value=(area.store_ids||[]).join(", ");
  root.querySelector(".remove").addEventListener("click",()=>{root.remove();updateAreaWarning()});
  root.querySelectorAll("input,select").forEach(input=>input.addEventListener("input",updateAreaWarning));
  el("regions").appendChild(root);updateAreaWarning();
}
function updateAreaWarning(){
  const count=document.querySelectorAll(".region-entry").length;
  el("areaWarning").hidden=count<2;
  el("areaEstimate").textContent="Approximately "+count+" pickup request"+(count===1?"":"s")+" per complete scan (before retries). The app checks areas sequentially. Maximum "+8+" areas.";
}
function loadForm(cfg){
  original=cfg; el("products").replaceChildren();el("regions").replaceChildren();
  Object.entries(cfg.products||{}).forEach(([id,p])=>productRow(id,p));
  const areas=Object.hasOwn(cfg,"monitoring_areas")?cfg.monitoring_areas:[
    ...Object.entries(cfg.search_zips||{}).map(([name,zip],i)=>({id:"us_"+(i+1),market:"US",location:zip,store_ids:[]})),
    ...(Object.values(cfg.products||{}).some(p=>p.market==="CA")&&cfg.ca_location?[{id:"ca_1",market:"CA",location:cfg.ca_location,store_ids:cfg.ca_target_store?[cfg.ca_target_store]:[]}]:[])
  ];
  areas.forEach(area=>regionRow(area));
  el("states").value=(cfg.allowed_states||[]).join(", ");
  el("priority").value=cfg.us_priority_store||"";
  el("caTax").value=Number(cfg.ca_tax_rate??0.13)*100;
  el("allStores").checked=!Object.hasOwn(cfg,"alert_store_ids");
  el("allProducts").checked=!Object.hasOwn(cfg,"alert_product_ids");
  el("alertStores").value=(cfg.alert_store_ids||[]).join(", ");
  el("alertProducts").value=(cfg.alert_product_ids||[]).join(", ");
  toggleAlertFields();updateAreaWarning();
}
function toggleAlertFields(){
  el("alertStores").disabled=el("allStores").checked;
  el("alertProducts").disabled=el("allProducts").checked;
}
function collect(){
  const data={...original,products:{},search_zips:{}};
  document.querySelectorAll(".product-entry").forEach(root=>{
    const id=root.querySelector(".pid").value.trim();
    if(!id)throw Error("Every product needs an ID.");
    if(Object.hasOwn(data.products,id))throw Error("Duplicate product ID: "+id);
    const market=root.querySelector(".market").value;
    const priceInput=root.querySelector(".price").value;
    if(priceInput==="")throw Error("Enter a price for "+id);
    data.products[id]={
      market,
      name:root.querySelector(".pname").value.trim(),
      part:root.querySelector(".sku").value.trim(),
      price:Number(priceInput),
      currency:market==="US"?"USD":"CAD"
    };
  });
  data.monitoring_areas=[];
  document.querySelectorAll(".region-entry").forEach(root=>{
    const id=root.querySelector(".areaId").value.trim();
    const market=root.querySelector(".country").value;
    const location=root.querySelector(".location").value.trim();
    if(!id)throw Error("Every monitoring area needs an ID.");
    data.monitoring_areas.push({id,market,location,store_ids:splitIds(root.querySelector(".areaStores").value)});
  });
  data.allowed_states=splitIds(el("states").value).map(s=>s.toUpperCase());
  data.us_priority_store=el("priority").value.trim();
  if(el("caTax").value==="")throw Error("Enter an estimated Canadian tax percentage.");
  data.ca_tax_rate=Number(el("caTax").value)/100;
  if(el("allStores").checked)delete data.alert_store_ids;
  else data.alert_store_ids=splitIds(el("alertStores").value);
  if(el("allProducts").checked)delete data.alert_product_ids;
  else data.alert_product_ids=splitIds(el("alertProducts").value);
  return data;
}
function status(message,error=false){el("message").textContent=message;el("message").style.color=error?"#ff7c8b":"#55e29d";}
async function start(){
  try{
    const r=await fetch("/api/config",{cache:"no-store"});
    const payload=await r.json();if(!r.ok)throw Error(payload.error||"Cannot read configuration");
    loadForm(payload.config);
    status(payload.exists?"Existing private configuration loaded.":"Example configuration loaded; save to create your own.");
  }catch(error){status(String(error),true);}
}
el("addProduct").addEventListener("click",()=>productRow("",{market:"US"}));
el("addRegion").addEventListener("click",()=>{
  const count=document.querySelectorAll(".region-entry").length;
  if(count>=8){status("Maximum 8 areas to protect Apple endpoints; remove an area first.",true);return}
  const existing=new Set([...document.querySelectorAll(".areaId")].map(v=>v.value));
  let n=1;while(existing.has("area_"+n))n++;
  regionRow({id:"area_"+n,market:"US",location:"",store_ids:[]});
});
el("allStores").addEventListener("change",toggleAlertFields);
el("allProducts").addEventListener("change",toggleAlertFields);
el("save").addEventListener("click",async()=>{
  const button=el("save");button.disabled=true;
  try{
    const data=collect();
    const r=await fetch("/api/config",{
      method:"POST",headers:{"Content-Type":"application/json","X-Setup-Token":TOKEN},
      body:JSON.stringify(data)
    });
    const response=await r.json();
    if(!r.ok)throw Error(response.error||"Save failed");
    loadForm(response.config);
    status("Saved locally. Restart your watcher to use the new settings.");
  }catch(error){status(error.message||String(error),true);}
  finally{button.disabled=false;}
});
start();
</script></body></html>"""


def create_wizard_app(config_path=None, sample_path=None):
    path = Path(config_path) if config_path is not None else ROOT / "config.json"
    example = Path(sample_path) if sample_path is not None else ROOT / "config.example.json"
    csrf_token = secrets.token_urlsafe(32)
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 65536

    @app.before_request
    def local_only():
        if request.remote_addr not in ("127.0.0.1", "::1", None):
            abort(403)
        if request.host.split(":")[0].lower() not in ("127.0.0.1", "localhost", "[::1]"):
            abort(403)

    @app.after_request
    def privacy_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/")
    def index():
        return render_template_string(WIZARD_HTML, token=csrf_token)

    @app.get("/api/config")
    def read_config():
        target = path if path.is_file() else example
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
            clean = validate_config(raw)
        except (OSError, ValueError) as exc:
            return jsonify({"error": f"Cannot read {target.name}: {exc}"}), 422
        # Keep unknown settings in the browser so they survive subsequent saves.
        return jsonify({"config": {**raw, **clean}, "exists": path.is_file()})

    @app.post("/api/config")
    def write_config():
        origin = request.headers.get("Origin")
        if origin and origin != request.host_url.rstrip("/"):
            return jsonify({"error": "Request origin not allowed"}), 403
        provided = request.headers.get("X-Setup-Token", "")
        if not hmac.compare_digest(provided, csrf_token):
            return jsonify({"error": "Setup token missing or invalid"}), 403
        try:
            incoming = request.get_json(silent=True)
            clean = validate_config(incoming)
            data = {**incoming, **clean}
            path.parent.mkdir(parents=True, exist_ok=True)
            # Preserve the most recent working configuration before replacing it.
            if path.is_file():
                previous = path.read_bytes()
                backup = path.with_name(path.name + ".bak")
                backup.write_bytes(previous)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent, prefix=".watcher-config-",
                suffix=".tmp", delete=False
            ) as temp:
                temp.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
                temp_path = Path(temp.name)
            try:
                os.replace(temp_path, path)
            finally:
                temp_path.unlink(missing_ok=True)
        except InvalidConfig as exc:
            return jsonify({"error": str(exc)}), 422
        except OSError as exc:
            return jsonify({"error": f"Could not save local configuration: {exc}"}), 500
        return jsonify({"saved": True, "config": data})

    return app


def main():
    parser = argparse.ArgumentParser(description="Edit Apple Watcher config in a local browser")
    parser.add_argument("--port", type=int, default=8091)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    print(f"Open http://127.0.0.1:{args.port} to configure the watcher.", flush=True)
    print("The wizard listens only on this computer. Press Ctrl+C to stop.", flush=True)
    create_wizard_app().run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
