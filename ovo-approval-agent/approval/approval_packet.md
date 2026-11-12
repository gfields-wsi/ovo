# OvO Merchant Approval Packet

Nothing in this packet is approved yet. Nothing is published.

Store: https://wsiventures.com/solemates.
Merchant: not supplied.
Tenant status: store_only_no_merchant_id.
Open questions: 0.

Presented rows: 36.
Rows under 50 percent, not presented: 0.
Rows with no accuracy value, not presented: 0.
Held rows: 88.

Accuracy values are taken as given. This agent does not re-check them.
The Enrichment Agent does the work.
The Coordinator owns the output.

## Card: 95 percent or better (reject_by_exception)
In a submitted group review, rows the merchant does not reject are approved.

- Trailhead Waterproof Hiking Boots, material_structured: now None, proposed Full-grain leather, waterproof membrane. Accuracy: 100.0 percent.
- Trailhead Waterproof Hiking Boots, fit_structured: now None, proposed True to size. Wide fit available in-store only — not in this demo catalog. Accuracy: 100.0 percent.
- Trailhead Waterproof Hiking Boots, returns_structured: now None, proposed 30-day returns, unworn. Accuracy: 100.0 percent.
- City Chelsea Rain Boots, material_structured: now None, proposed Rubber upper, textile lining. Accuracy: 100.0 percent.
- City Chelsea Rain Boots, fit_structured: now None, proposed True to size. Narrower than the Trailhead boots. Accuracy: 100.0 percent.
- City Chelsea Rain Boots, returns_structured: now None, proposed 30-day returns, unworn. Accuracy: 100.0 percent.
- Boardwalk Leather Sandals, material_structured: now None, proposed Leather straps, cork footbed. Accuracy: 100.0 percent.
- Boardwalk Leather Sandals, fit_structured: now None, proposed True to size. Break in over 2–3 wears. Accuracy: 100.0 percent.
- Boardwalk Leather Sandals, returns_structured: now None, proposed 30-day returns, unworn. Accuracy: 100.0 percent.
- Cloudstep Sport Sandals, material_structured: now None, proposed Synthetic straps, EVA sole. Accuracy: 100.0 percent.
- Cloudstep Sport Sandals, fit_structured: now None, proposed Runs slightly large — consider half a size down. Accuracy: 100.0 percent.
- Cloudstep Sport Sandals, returns_structured: now None, proposed 30-day returns, unworn. Accuracy: 100.0 percent.
- Court Classic White Sneakers, material_structured: now None, proposed Leather upper, rubber cupsole. Accuracy: 100.0 percent.
- Court Classic White Sneakers, fit_structured: now None, proposed True to size. Accuracy: 100.0 percent.
- Court Classic White Sneakers, returns_structured: now None, proposed 30-day returns, unworn. Accuracy: 100.0 percent.
- Retro High-Top Sneakers, material_structured: now None, proposed Canvas upper, rubber sole. Accuracy: 100.0 percent.
- Retro High-Top Sneakers, fit_structured: now None, proposed True to size. High-top fit — ankle support, less flex. Accuracy: 100.0 percent.
- Retro High-Top Sneakers, returns_structured: now None, proposed 30-day returns, unworn. Accuracy: 100.0 percent.
- Fireside Wool Slippers, material_structured: now None, proposed Wool felt upper, suede sole. Accuracy: 100.0 percent.
- Fireside Wool Slippers, fit_structured: now None, proposed True to size. Wool will mould slightly with wear. Accuracy: 100.0 percent.
- Fireside Wool Slippers, returns_structured: now None, proposed 30-day returns, unworn. Accuracy: 100.0 percent.
- Cloud Plush House Slippers, material_structured: now None, proposed Plush synthetic upper, rubber sole. Accuracy: 100.0 percent.
- Cloud Plush House Slippers, fit_structured: now None, proposed Runs slightly small — consider half a size up. Accuracy: 100.0 percent.
- Cloud Plush House Slippers, returns_structured: now None, proposed 30-day returns, unworn. Accuracy: 100.0 percent.
- Velocity Road Runners, material_structured: now None, proposed Engineered mesh, EVA midsole. Accuracy: 100.0 percent.
- Velocity Road Runners, fit_structured: now None, proposed True to size. Best for road running and daily training. Accuracy: 100.0 percent.
- Velocity Road Runners, returns_structured: now None, proposed 30-day returns, unworn. Accuracy: 100.0 percent.
- Trailblazer Trail Runners, material_structured: now None, proposed Ripstop mesh, aggressive tread. Accuracy: 100.0 percent.
- Trailblazer Trail Runners, fit_structured: now None, proposed True to size. Half a size up if you wear thick trail socks. Accuracy: 100.0 percent.
- Trailblazer Trail Runners, returns_structured: now None, proposed 30-day returns, unworn. Accuracy: 100.0 percent.
- Marathon Knit Runners, material_structured: now None, proposed Knit upper, foam midsole. Accuracy: 100.0 percent.
- Marathon Knit Runners, fit_structured: now None, proposed True to size. Knit upper stretches slightly. Accuracy: 100.0 percent.
- Marathon Knit Runners, returns_structured: now None, proposed 30-day returns, unworn. Accuracy: 100.0 percent.
- Everyday Comfort Runners, material_structured: now None, proposed Mesh upper, cushioned sole. Accuracy: 100.0 percent.
- Everyday Comfort Runners, fit_structured: now None, proposed True to size. Roomy toe box. Accuracy: 100.0 percent.
- Everyday Comfort Runners, returns_structured: now None, proposed 30-day returns, unworn. Accuracy: 100.0 percent.

## Card: 80 to 94 percent (approve_individual)
The merchant approves each row they want. Rows not explicitly approved are not approved.


## Card: 50 to 79 percent (approve_individual)
The merchant approves each row they want. Rows not explicitly approved are not approved.


The merchant can correct a value.
The merchant can add information for a held row.
Corrections and additions are recorded exactly as given.
They are marked merchant supplied.
Full card edit design comes later.
The decision file supports corrections and additions now.
The merchant can ask a question on a row or a group.
A row with an open question is not approved.
A row with an open question is not rejected.
The merchant can close a question, then decide the row.

Copy decision_template.json.
Fill approved_by.
Fill the session object with your merchant session.
A typed name alone is not authority.
The session store ID must match this packet.
Submit each group you decide.
In the 95 percent or better group, list rejections only.
Rows not rejected are approved.
In the 80 to 94 and 50 to 79 groups, list each row you approve.
Rows not listed are not approved.
A group that is not submitted gives no approval.
