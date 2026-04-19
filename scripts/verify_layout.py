import zipfile, json
z = zipfile.ZipFile(r"C:\TM_PBI\TMR_p1_dashboard.pbix")
raw = z.open("Report/Layout").read().decode("utf-16-le")
layout = json.loads(raw)
sec = layout["sections"][0]
print("Page:", sec["displayName"])
print("Canvas: {}x{}".format(sec["width"], sec["height"]))
print("Visuals:", len(sec["visualContainers"]))
for v in sec["visualContainers"]:
    cfg = json.loads(v["config"])
    vt = cfg.get("singleVisual", {}).get("visualType", "textbox")
    print("  id={} type={:15s} x={:4d} y={:4d} w={:4d} h={:4d}".format(
        v["id"], vt, int(v["x"]), int(v["y"]), int(v["width"]), int(v["height"])))
z.close()
