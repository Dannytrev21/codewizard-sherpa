---
a0: &a0 [hostile, payload]
a1: &a1 [*a0, *a0, *a0, *a0]
a2: &a2 [*a1, *a1, *a1, *a1]
a3: &a3 [*a2, *a2, *a2, *a2]
a4: &a4 [*a3, *a3, *a3, *a3]
a5: &a5 [*a4, *a4, *a4, *a4]
a6: &a6 [*a5, *a5, *a5, *a5]
a7: &a7 [*a6, *a6, *a6, *a6]
a8: &a8 [*a7, *a7, *a7, *a7]
root: *a8
---
Case 8 — alias-chain fan-out (billion-laughs-style). Expected to either hit DepthCapExceeded or yield a deeply-nested expansion the depth walker refuses; loader surfaces unsafe_yaml.
