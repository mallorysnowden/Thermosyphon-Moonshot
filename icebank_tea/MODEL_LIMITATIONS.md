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
- **Usable water temperature is set per case** (liquid-cooled data center 27 degC, air-cooled 13 degC, hospital 4 degC, salmon 1.5 degC,
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
- **Time-of-use prices are approximate.** On/off-peak spreads come from Xcel base energy charges (ND D17; SD
  General TOD as a proxy for MN) with a flat adder that keeps each case's average price; holidays are ignored and
  the series is assumed to start on a Monday. Wholesale or real-time prices are not modelled.
- **Dry cooler is simple.** Sensible cooling of liquid pit water only (above 1 degC), linear in the water-air
  temperature difference, fans at full power whenever it runs; $70/kW at a 10 K ITD is an assumption.
- **Off-peak charging is rule-based, not optimised.** When allowed (off-peak hours in months with load), the 30%
  chiller charges at whatever capacity it has spare until the pit is full, with no weather or price forecast.
  A smarter controller could do somewhat better. Full-backup charging is not modelled.
- **No value for freed electrical capacity** beyond the electrical-service credit, no carbon price, and no
  learning curve between FOAK and NOAK.
- **Hospital heating is a simple profile.** Heat demand is a 25% year-round floor plus space heat linear in
  outdoor temperature below 15 degC, scaled to an assumed 80 kBtu/ft2-yr for a 300,000 ft2 hospital; there is
  no occupancy, solar or ventilation schedule. Steam for sterilisers and humidifiers stays on boilers in every
  option and is left out, and boiler capital is assumed to cancel because boilers stay as backup in all options.
- **Heat pumps are rules of thumb.** Pit heat pump: half of Carnot, 55 degC supply, evaporating 5 K below the pit
  water, $400/kW plus $30/kW of brine coils (assumptions); it extracts heat as uniform ice in the pit and stops
  when the pit's ice cap is reached. Air-source heat pumps: 45% of Carnot, clipped to COP 1.3-4.5, $600/kW, with
  no defrost penalty or loss of capacity in the cold beyond the COP. Neither plant is given N+1 redundancy.
- **The BAU hospital has no heat-recovery chiller.** Many modern hospitals recover chiller condenser heat for
  summer reheat; that would make BAU cheaper in both B and F. Heat-pump and thermosiphon power are tallied on the
  main pit trajectory for every configuration, including the off-peak-charging one.
- **The heat-pump reserve uses the average heating profile** (no weather forecast), and thermosiphons are either
  fully on or valved off.

