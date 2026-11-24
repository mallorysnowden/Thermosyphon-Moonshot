# Model limitations

- **Synthetic weather.** Hourly temperatures come from monthly normals plus random day-to-day weather, tuned
  roughly (Fargo gets ~8 days >= 90 degF vs 12.7 observed). Winters are drawn independently; the worst of 12
  years is roughly a 1-in-12-year event. Replace with real hourly records (`weather.load_csv`) before relying
  on fill dates or reliability.
- **One calibration point for the condenser.** 5 W/m2K on dense-fin area fits Li et al. (2020), one 8 m unit
  near Beijing, at an assumed ~2.5 m/s wind. Wind, snow and rime on fins are not modelled.
- **Simple store physics.** Identical cells, well-mixed water, quasi-steady ice conduction, no ice sensible
  heat below 0 degC, no natural ice growth on the pit surface, no stratification. Ice melts from the outside
  of each icicle as discharge water flows past.
- **Dispatch is ice first**; a backup chiller only covers what the store cannot.
- **Usable water temperature is set per case** (data center 27 degC, hospital 4 degC, salmon 1.5 degC,
  process 3 degC). For the data center this counts a lot of sensible storage in warm meltwater.
- **Salmon ice-only chills to about +1 degC**, not the -1 degC of refrigerated seawater.
- **Costs are estimates, not quotes:** the finished/raw index, installation, field joints, pit cost curve and
  ice premium, discharge plant, electrical-service credit and O&M are all assumptions with ranges.
- **Ammonia regulation not costed.** An ice-only data center store holds ~9 t of ammonia (30,000 units x
  0.3 kg), above the 4.5 t OSHA PSM / EPA RMP threshold if regulators treat the field as one process.
- **Demand charges are simplified.** The chiller's monthly peak draw is assumed to add fully to the site's
  monthly billed peak. Ratchets (Xcel ND bills at least 50% of the prior 11 months' peak), the ND interim rate
  surcharge, power factor and coincident-peak or special large-load contracts are not modelled; the x0 / x2
  sensitivity brackets them. The hospital uses Xcel MN's proposed 2026 rates. The salmon plant uses Nushagak
  Cooperative's seasonal rate because Naknek Electric's tariff is not online; a self-generating plant pays
  no demand charge.
- **Water and auxiliaries are rules of thumb.** Tower evaporation is 1.6 m3 per MWh of heat rejected at 4 cycles of
  concentration; auxiliaries are 0.015 kW per kW of cooling for chilled-water pumps (+0.03 for condenser pumps and
  tower fans). The data-center tower variant uses a crude wet-bulb proxy, as the synthetic weather has no humidity.
  The salmon plant's water price is an assumption. Dry coolers ahead of the data-center trim are identical in both
  options and are not costed in either.
- **No value for freed electrical capacity** beyond the electrical-service credit, no carbon price, and no
  learning curve between FOAK and NOAK.
