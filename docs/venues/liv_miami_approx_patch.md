# LIV Miami (approximate recreation) - demo patch sheet

**APPROXIMATE RECREATION of LIV Miami (Fontainebleau Miami Beach), built from public 2009 trade press. It is NOT LIV's real patch, plot or addressing, and is not endorsed by or affiliated with the venue.**

131 fixtures on universe(s) 0, 1, 2, 3. Every fixture is patched on this system's generic demo profile for its type, not on the source fixture's own DMX personality.

Generated from the 'liv_miami_approx' venue preset by scripts/export_demo_patch_sheet.py - edit the preset, not this file.

## Universes

| Universe | Fixtures | Channels used | Last channel |
| --- | --- | --- | --- |
| 0 | 34 | 512 | 512 |
| 1 | 48 | 512 | 512 |
| 2 | 20 | 240 | 240 |
| 3 | 29 | 348 | 348 |

## Groups

The names a look selects on. The engine adds its own groups by type and by position on top of these.

| Group | Fixtures |
| --- | --- |
| `floor_spots` | 22 |
| `spots_chord_a` | 5 |
| `spots_left` | 10 |
| `spots_right` | 10 |
| `spots_chord_b` | 6 |
| `spots_chord_c` | 6 |
| `spots_chord_d` | 5 |
| `balcony_spots` | 4 |
| `centre_washes` | 8 |
| `dome_pixels` | 44 |
| `dome_spokes` | 32 |
| `dome_spokes_inner` | 16 |
| `dome_spokes_outer` | 16 |
| `led_strips` | 8 |
| `booth_strips` | 4 |
| `dj_booth` | 33 |
| `skybox_strips` | 4 |
| `truss_strobes` | 8 |
| `dome_rim` | 12 |
| `led_pars` | 10 |
| `wall_pars` | 6 |
| `staircase_pars` | 2 |
| `led_wall` | 27 |
| `led_wall_centre` | 15 |
| `led_wall_wings` | 12 |
| `booth_wash` | 2 |

## Patch

Positions are metres from the centre of the floor: X across, Y up, Z toward the rear of the room. Rotation is degrees about X / Y / Z.

| # | Fixture ID | Name | Profile | Mode | Channels | Universe | Address | Group | Groups | X | Y | Z | Rotation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `ds575_a1` | Design Spot A1 | Elation Design Spot 575E (as generic mover) | Demo generic 16ch | 16 | 0 | 1 | Dance Floor Spots | floor_spots; spots_chord_a; spots_left | -6.00 | 6.50 | -7.50 | 0 / 0 / 0 |
| 2 | `ds575_a2` | Design Spot A2 | Elation Design Spot 575E (as generic mover) | Demo generic 16ch | 16 | 0 | 17 | Dance Floor Spots | floor_spots; spots_chord_a; spots_left | -3.00 | 6.50 | -7.50 | 0 / 0 / 0 |
| 3 | `ds575_a3` | Design Spot A3 | Elation Design Spot 575E (as generic mover) | Demo generic 16ch | 16 | 0 | 33 | Dance Floor Spots | floor_spots; spots_chord_a | 0.00 | 6.50 | -7.50 | 0 / 0 / 0 |
| 4 | `ds575_a4` | Design Spot A4 | Elation Design Spot 575E (as generic mover) | Demo generic 16ch | 16 | 0 | 49 | Dance Floor Spots | floor_spots; spots_chord_a; spots_right | 3.00 | 6.50 | -7.50 | 0 / 0 / 0 |
| 5 | `ds575_a5` | Design Spot A5 | Elation Design Spot 575E (as generic mover) | Demo generic 16ch | 16 | 0 | 65 | Dance Floor Spots | floor_spots; spots_chord_a; spots_right | 6.00 | 6.50 | -7.50 | 0 / 0 / 0 |
| 6 | `ds575_b1` | Design Spot B1 | Elation Design Spot 575E (as generic mover) | Demo generic 16ch | 16 | 0 | 81 | Dance Floor Spots | floor_spots; spots_chord_b; spots_left | -9.00 | 6.50 | -2.50 | 0 / 0 / 0 |
| 7 | `ds575_b2` | Design Spot B2 | Elation Design Spot 575E (as generic mover) | Demo generic 16ch | 16 | 0 | 97 | Dance Floor Spots | floor_spots; spots_chord_b; spots_left | -5.40 | 6.50 | -2.50 | 0 / 0 / 0 |
| 8 | `ds575_b3` | Design Spot B3 | Elation Design Spot 575E (as generic mover) | Demo generic 16ch | 16 | 0 | 113 | Dance Floor Spots | floor_spots; spots_chord_b; spots_left | -1.80 | 6.50 | -2.50 | 0 / 0 / 0 |
| 9 | `ds575_b4` | Design Spot B4 | Elation Design Spot 575E (as generic mover) | Demo generic 16ch | 16 | 0 | 129 | Dance Floor Spots | floor_spots; spots_chord_b; spots_right | 1.80 | 6.50 | -2.50 | 0 / 0 / 0 |
| 10 | `ds575_b5` | Design Spot B5 | Elation Design Spot 575E (as generic mover) | Demo generic 16ch | 16 | 0 | 145 | Dance Floor Spots | floor_spots; spots_chord_b; spots_right | 5.40 | 6.50 | -2.50 | 0 / 0 / 0 |
| 11 | `ds575_b6` | Design Spot B6 | Elation Design Spot 575E (as generic mover) | Demo generic 16ch | 16 | 0 | 161 | Dance Floor Spots | floor_spots; spots_chord_b; spots_right | 9.00 | 6.50 | -2.50 | 0 / 0 / 0 |
| 12 | `ds575_c1` | Design Spot C1 | Elation Design Spot 575E (as generic mover) | Demo generic 16ch | 16 | 0 | 177 | Dance Floor Spots | floor_spots; spots_chord_c; spots_left | -9.00 | 6.50 | 2.50 | 0 / 0 / 0 |
| 13 | `ds575_c2` | Design Spot C2 | Elation Design Spot 575E (as generic mover) | Demo generic 16ch | 16 | 0 | 193 | Dance Floor Spots | floor_spots; spots_chord_c; spots_left | -5.40 | 6.50 | 2.50 | 0 / 0 / 0 |
| 14 | `ds575_c3` | Design Spot C3 | Elation Design Spot 575E (as generic mover) | Demo generic 16ch | 16 | 0 | 209 | Dance Floor Spots | floor_spots; spots_chord_c; spots_left | -1.80 | 6.50 | 2.50 | 0 / 0 / 0 |
| 15 | `ds575_c4` | Design Spot C4 | Elation Design Spot 575E (as generic mover) | Demo generic 16ch | 16 | 0 | 225 | Dance Floor Spots | floor_spots; spots_chord_c; spots_right | 1.80 | 6.50 | 2.50 | 0 / 0 / 0 |
| 16 | `ds575_c5` | Design Spot C5 | Elation Design Spot 575E (as generic mover) | Demo generic 16ch | 16 | 0 | 241 | Dance Floor Spots | floor_spots; spots_chord_c; spots_right | 5.40 | 6.50 | 2.50 | 0 / 0 / 0 |
| 17 | `ds575_c6` | Design Spot C6 | Elation Design Spot 575E (as generic mover) | Demo generic 16ch | 16 | 0 | 257 | Dance Floor Spots | floor_spots; spots_chord_c; spots_right | 9.00 | 6.50 | 2.50 | 0 / 0 / 0 |
| 18 | `ds575_d1` | Design Spot D1 | Elation Design Spot 575E (as generic mover) | Demo generic 16ch | 16 | 0 | 273 | Dance Floor Spots | floor_spots; spots_chord_d; spots_left | -6.00 | 6.50 | 7.50 | 0 / 0 / 0 |
| 19 | `ds575_d2` | Design Spot D2 | Elation Design Spot 575E (as generic mover) | Demo generic 16ch | 16 | 0 | 289 | Dance Floor Spots | floor_spots; spots_chord_d; spots_left | -3.00 | 6.50 | 7.50 | 0 / 0 / 0 |
| 20 | `ds575_d3` | Design Spot D3 | Elation Design Spot 575E (as generic mover) | Demo generic 16ch | 16 | 0 | 305 | Dance Floor Spots | floor_spots; spots_chord_d | 0.00 | 6.50 | 7.50 | 0 / 0 / 0 |
| 21 | `ds575_d4` | Design Spot D4 | Elation Design Spot 575E (as generic mover) | Demo generic 16ch | 16 | 0 | 321 | Dance Floor Spots | floor_spots; spots_chord_d; spots_right | 3.00 | 6.50 | 7.50 | 0 / 0 / 0 |
| 22 | `ds575_d5` | Design Spot D5 | Elation Design Spot 575E (as generic mover) | Demo generic 16ch | 16 | 0 | 337 | Dance Floor Spots | floor_spots; spots_chord_d; spots_right | 6.00 | 6.50 | 7.50 | 0 / 0 / 0 |
| 23 | `ds300_1` | Mezzanine Spot 1 | Elation Design Spot 300E (as generic spot) | Demo generic 12ch | 12 | 0 | 353 | Mezzanine Spots | balcony_spots | -7.50 | 4.00 | 11.00 | 0 / 0 / 0 |
| 24 | `ds300_2` | Mezzanine Spot 2 | Elation Design Spot 300E (as generic spot) | Demo generic 12ch | 12 | 0 | 365 | Mezzanine Spots | balcony_spots | -2.50 | 4.00 | 11.00 | 0 / 0 / 0 |
| 25 | `ds300_3` | Mezzanine Spot 3 | Elation Design Spot 300E (as generic spot) | Demo generic 12ch | 12 | 0 | 377 | Mezzanine Spots | balcony_spots | 2.50 | 4.00 | 11.00 | 0 / 0 / 0 |
| 26 | `ds300_4` | Mezzanine Spot 4 | Elation Design Spot 300E (as generic spot) | Demo generic 12ch | 12 | 0 | 389 | Mezzanine Spots | balcony_spots | 7.50 | 4.00 | 11.00 | 0 / 0 / 0 |
| 27 | `imp_1` | Impression Wash 1 | Elation Impression RGB (as generic wash) | Demo generic 14ch | 14 | 0 | 401 | Dome Centre Washes | centre_washes | -3.60 | 3.05 | -1.50 | 0 / 0 / 0 |
| 28 | `imp_2` | Impression Wash 2 | Elation Impression RGB (as generic wash) | Demo generic 14ch | 14 | 0 | 415 | Dome Centre Washes | centre_washes | -1.20 | 3.05 | -1.50 | 0 / 0 / 0 |
| 29 | `imp_3` | Impression Wash 3 | Elation Impression RGB (as generic wash) | Demo generic 14ch | 14 | 0 | 429 | Dome Centre Washes | centre_washes | 1.20 | 3.05 | -1.50 | 0 / 0 / 0 |
| 30 | `imp_4` | Impression Wash 4 | Elation Impression RGB (as generic wash) | Demo generic 14ch | 14 | 0 | 443 | Dome Centre Washes | centre_washes | 3.60 | 3.05 | -1.50 | 0 / 0 / 0 |
| 31 | `imp_5` | Impression Wash 5 | Elation Impression RGB (as generic wash) | Demo generic 14ch | 14 | 0 | 457 | Dome Centre Washes | centre_washes | -3.60 | 3.05 | 1.50 | 0 / 0 / 0 |
| 32 | `imp_6` | Impression Wash 6 | Elation Impression RGB (as generic wash) | Demo generic 14ch | 14 | 0 | 471 | Dome Centre Washes | centre_washes | -1.20 | 3.05 | 1.50 | 0 / 0 / 0 |
| 33 | `imp_7` | Impression Wash 7 | Elation Impression RGB (as generic wash) | Demo generic 14ch | 14 | 0 | 485 | Dome Centre Washes | centre_washes | 1.20 | 3.05 | 1.50 | 0 / 0 / 0 |
| 34 | `imp_8` | Impression Wash 8 | Elation Impression RGB (as generic wash) | Demo generic 14ch | 14 | 0 | 499 | Dome Centre Washes | centre_washes | 3.60 | 3.05 | 1.50 | 0 / 0 / 0 |
| 35 | `dome_s1a` | Dome Spoke 1 Inner | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 1 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_inner | 0.68 | 8.60 | -3.43 | 0 / 0 / 0 |
| 36 | `dome_s1b` | Dome Spoke 1 Outer | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 13 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_outer | 1.66 | 7.80 | -8.34 | 0 / 0 / 0 |
| 37 | `dome_s2a` | Dome Spoke 2 Inner | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 25 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_inner | 1.94 | 8.60 | -2.91 | 0 / 0 / 0 |
| 38 | `dome_s2b` | Dome Spoke 2 Outer | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 37 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_outer | 4.72 | 7.80 | -7.07 | 0 / 0 / 0 |
| 39 | `dome_s3a` | Dome Spoke 3 Inner | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 49 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_inner | 2.91 | 8.60 | -1.94 | 0 / 0 / 0 |
| 40 | `dome_s3b` | Dome Spoke 3 Outer | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 61 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_outer | 7.07 | 7.80 | -4.72 | 0 / 0 / 0 |
| 41 | `dome_s4a` | Dome Spoke 4 Inner | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 73 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_inner | 3.43 | 8.60 | -0.68 | 0 / 0 / 0 |
| 42 | `dome_s4b` | Dome Spoke 4 Outer | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 85 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_outer | 8.34 | 7.80 | -1.66 | 0 / 0 / 0 |
| 43 | `dome_s5a` | Dome Spoke 5 Inner | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 97 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_inner | 3.43 | 8.60 | 0.68 | 0 / 0 / 0 |
| 44 | `dome_s5b` | Dome Spoke 5 Outer | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 109 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_outer | 8.34 | 7.80 | 1.66 | 0 / 0 / 0 |
| 45 | `dome_s6a` | Dome Spoke 6 Inner | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 121 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_inner | 2.91 | 8.60 | 1.94 | 0 / 0 / 0 |
| 46 | `dome_s6b` | Dome Spoke 6 Outer | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 133 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_outer | 7.07 | 7.80 | 4.72 | 0 / 0 / 0 |
| 47 | `dome_s7a` | Dome Spoke 7 Inner | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 145 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_inner | 1.94 | 8.60 | 2.91 | 0 / 0 / 0 |
| 48 | `dome_s7b` | Dome Spoke 7 Outer | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 157 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_outer | 4.72 | 7.80 | 7.07 | 0 / 0 / 0 |
| 49 | `dome_s8a` | Dome Spoke 8 Inner | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 169 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_inner | 0.68 | 8.60 | 3.43 | 0 / 0 / 0 |
| 50 | `dome_s8b` | Dome Spoke 8 Outer | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 181 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_outer | 1.66 | 7.80 | 8.34 | 0 / 0 / 0 |
| 51 | `dome_s9a` | Dome Spoke 9 Inner | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 193 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_inner | -0.68 | 8.60 | 3.43 | 0 / 0 / 0 |
| 52 | `dome_s9b` | Dome Spoke 9 Outer | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 205 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_outer | -1.66 | 7.80 | 8.34 | 0 / 0 / 0 |
| 53 | `dome_s10a` | Dome Spoke 10 Inner | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 217 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_inner | -1.94 | 8.60 | 2.91 | 0 / 0 / 0 |
| 54 | `dome_s10b` | Dome Spoke 10 Outer | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 229 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_outer | -4.72 | 7.80 | 7.07 | 0 / 0 / 0 |
| 55 | `dome_s11a` | Dome Spoke 11 Inner | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 241 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_inner | -2.91 | 8.60 | 1.94 | 0 / 0 / 0 |
| 56 | `dome_s11b` | Dome Spoke 11 Outer | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 253 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_outer | -7.07 | 7.80 | 4.72 | 0 / 0 / 0 |
| 57 | `dome_s12a` | Dome Spoke 12 Inner | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 265 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_inner | -3.43 | 8.60 | 0.68 | 0 / 0 / 0 |
| 58 | `dome_s12b` | Dome Spoke 12 Outer | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 277 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_outer | -8.34 | 7.80 | 1.66 | 0 / 0 / 0 |
| 59 | `dome_s13a` | Dome Spoke 13 Inner | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 289 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_inner | -3.43 | 8.60 | -0.68 | 0 / 0 / 0 |
| 60 | `dome_s13b` | Dome Spoke 13 Outer | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 301 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_outer | -8.34 | 7.80 | -1.66 | 0 / 0 / 0 |
| 61 | `dome_s14a` | Dome Spoke 14 Inner | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 313 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_inner | -2.91 | 8.60 | -1.94 | 0 / 0 / 0 |
| 62 | `dome_s14b` | Dome Spoke 14 Outer | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 325 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_outer | -7.07 | 7.80 | -4.72 | 0 / 0 / 0 |
| 63 | `dome_s15a` | Dome Spoke 15 Inner | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 337 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_inner | -1.94 | 8.60 | -2.91 | 0 / 0 / 0 |
| 64 | `dome_s15b` | Dome Spoke 15 Outer | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 349 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_outer | -4.72 | 7.80 | -7.07 | 0 / 0 / 0 |
| 65 | `dome_s16a` | Dome Spoke 16 Inner | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 361 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_inner | -0.68 | 8.60 | -3.43 | 0 / 0 / 0 |
| 66 | `dome_s16b` | Dome Spoke 16 Outer | Color Kinetics iColor Cove MX (as generic bar) | Demo generic 12ch | 12 | 1 | 373 | Dome Spokes | dome_pixels; dome_spokes; dome_spokes_outer | -1.66 | 7.80 | -8.34 | 0 / 0 / 0 |
| 67 | `dled_booth1` | Booth Strip 1 | Elation DLED 60 Strip (as generic bar) | Demo generic 12ch | 12 | 1 | 385 | Booth Strips | led_strips; booth_strips; dj_booth | -2.70 | 1.00 | -12.10 | 0 / 0 / 0 |
| 68 | `dled_booth2` | Booth Strip 2 | Elation DLED 60 Strip (as generic bar) | Demo generic 12ch | 12 | 1 | 397 | Booth Strips | led_strips; booth_strips; dj_booth | -0.90 | 1.00 | -12.10 | 0 / 0 / 0 |
| 69 | `dled_booth3` | Booth Strip 3 | Elation DLED 60 Strip (as generic bar) | Demo generic 12ch | 12 | 1 | 409 | Booth Strips | led_strips; booth_strips; dj_booth | 0.90 | 1.00 | -12.10 | 0 / 0 / 0 |
| 70 | `dled_booth4` | Booth Strip 4 | Elation DLED 60 Strip (as generic bar) | Demo generic 12ch | 12 | 1 | 421 | Booth Strips | led_strips; booth_strips; dj_booth | 2.70 | 1.00 | -12.10 | 0 / 0 / 0 |
| 71 | `dled_sky1` | Skybox Strip 1 | Elation DLED 60 Strip (as generic bar) | Demo generic 12ch | 12 | 1 | 433 | Skybox Strips | led_strips; skybox_strips | -13.30 | 3.60 | -4.00 | 0 / 0 / 0 |
| 72 | `dled_sky2` | Skybox Strip 2 | Elation DLED 60 Strip (as generic bar) | Demo generic 12ch | 12 | 1 | 445 | Skybox Strips | led_strips; skybox_strips | -13.30 | 3.60 | 4.00 | 0 / 0 / 0 |
| 73 | `dled_sky3` | Skybox Strip 3 | Elation DLED 60 Strip (as generic bar) | Demo generic 12ch | 12 | 1 | 457 | Skybox Strips | led_strips; skybox_strips | 13.30 | 3.60 | -4.00 | 0 / 0 / 0 |
| 74 | `dled_sky4` | Skybox Strip 4 | Elation DLED 60 Strip (as generic bar) | Demo generic 12ch | 12 | 1 | 469 | Skybox Strips | led_strips; skybox_strips | 13.30 | 3.60 | 4.00 | 0 / 0 / 0 |
| 75 | `atomic_1` | Atomic Strobe 1 | Martin Atomic 3000 DMX (as generic strobe) | Demo generic 4ch | 4 | 1 | 481 | Strobes | truss_strobes | -8.00 | 6.50 | -7.50 | 0 / 0 / 0 |
| 76 | `atomic_2` | Atomic Strobe 2 | Martin Atomic 3000 DMX (as generic strobe) | Demo generic 4ch | 4 | 1 | 485 | Strobes | truss_strobes | 8.00 | 6.50 | -7.50 | 0 / 0 / 0 |
| 77 | `atomic_3` | Atomic Strobe 3 | Martin Atomic 3000 DMX (as generic strobe) | Demo generic 4ch | 4 | 1 | 489 | Strobes | truss_strobes | -10.50 | 6.50 | -2.50 | 0 / 0 / 0 |
| 78 | `atomic_4` | Atomic Strobe 4 | Martin Atomic 3000 DMX (as generic strobe) | Demo generic 4ch | 4 | 1 | 493 | Strobes | truss_strobes | 10.50 | 6.50 | -2.50 | 0 / 0 / 0 |
| 79 | `atomic_5` | Atomic Strobe 5 | Martin Atomic 3000 DMX (as generic strobe) | Demo generic 4ch | 4 | 1 | 497 | Strobes | truss_strobes | -10.50 | 6.50 | 2.50 | 0 / 0 / 0 |
| 80 | `atomic_6` | Atomic Strobe 6 | Martin Atomic 3000 DMX (as generic strobe) | Demo generic 4ch | 4 | 1 | 501 | Strobes | truss_strobes | 10.50 | 6.50 | 2.50 | 0 / 0 / 0 |
| 81 | `atomic_7` | Atomic Strobe 7 | Martin Atomic 3000 DMX (as generic strobe) | Demo generic 4ch | 4 | 1 | 505 | Strobes | truss_strobes | -8.00 | 6.50 | 7.50 | 0 / 0 / 0 |
| 82 | `atomic_8` | Atomic Strobe 8 | Martin Atomic 3000 DMX (as generic strobe) | Demo generic 4ch | 4 | 1 | 509 | Strobes | truss_strobes | 8.00 | 6.50 | 7.50 | 0 / 0 / 0 |
| 83 | `dome_rim1` | Dome Rim 1 | Color Kinetics ColorBlast 12 (as generic par) | Demo generic 12ch | 12 | 2 | 1 | Dome Rim | dome_pixels; dome_rim | 3.34 | 7.00 | -12.46 | 0 / 0 / 0 |
| 84 | `dome_rim2` | Dome Rim 2 | Color Kinetics ColorBlast 12 (as generic par) | Demo generic 12ch | 12 | 2 | 13 | Dome Rim | dome_pixels; dome_rim | 9.12 | 7.00 | -9.12 | 0 / 0 / 0 |
| 85 | `dome_rim3` | Dome Rim 3 | Color Kinetics ColorBlast 12 (as generic par) | Demo generic 12ch | 12 | 2 | 25 | Dome Rim | dome_pixels; dome_rim | 12.46 | 7.00 | -3.34 | 0 / 0 / 0 |
| 86 | `dome_rim4` | Dome Rim 4 | Color Kinetics ColorBlast 12 (as generic par) | Demo generic 12ch | 12 | 2 | 37 | Dome Rim | dome_pixels; dome_rim | 12.46 | 7.00 | 3.34 | 0 / 0 / 0 |
| 87 | `dome_rim5` | Dome Rim 5 | Color Kinetics ColorBlast 12 (as generic par) | Demo generic 12ch | 12 | 2 | 49 | Dome Rim | dome_pixels; dome_rim | 9.12 | 7.00 | 9.12 | 0 / 0 / 0 |
| 88 | `dome_rim6` | Dome Rim 6 | Color Kinetics ColorBlast 12 (as generic par) | Demo generic 12ch | 12 | 2 | 61 | Dome Rim | dome_pixels; dome_rim | 3.34 | 7.00 | 12.46 | 0 / 0 / 0 |
| 89 | `dome_rim7` | Dome Rim 7 | Color Kinetics ColorBlast 12 (as generic par) | Demo generic 12ch | 12 | 2 | 73 | Dome Rim | dome_pixels; dome_rim | -3.34 | 7.00 | 12.46 | 0 / 0 / 0 |
| 90 | `dome_rim8` | Dome Rim 8 | Color Kinetics ColorBlast 12 (as generic par) | Demo generic 12ch | 12 | 2 | 85 | Dome Rim | dome_pixels; dome_rim | -9.12 | 7.00 | 9.12 | 0 / 0 / 0 |
| 91 | `dome_rim9` | Dome Rim 9 | Color Kinetics ColorBlast 12 (as generic par) | Demo generic 12ch | 12 | 2 | 97 | Dome Rim | dome_pixels; dome_rim | -12.46 | 7.00 | 3.34 | 0 / 0 / 0 |
| 92 | `dome_rim10` | Dome Rim 10 | Color Kinetics ColorBlast 12 (as generic par) | Demo generic 12ch | 12 | 2 | 109 | Dome Rim | dome_pixels; dome_rim | -12.46 | 7.00 | -3.34 | 0 / 0 / 0 |
| 93 | `dome_rim11` | Dome Rim 11 | Color Kinetics ColorBlast 12 (as generic par) | Demo generic 12ch | 12 | 2 | 121 | Dome Rim | dome_pixels; dome_rim | -9.12 | 7.00 | -9.12 | 0 / 0 / 0 |
| 94 | `dome_rim12` | Dome Rim 12 | Color Kinetics ColorBlast 12 (as generic par) | Demo generic 12ch | 12 | 2 | 133 | Dome Rim | dome_pixels; dome_rim | -3.34 | 7.00 | -12.46 | 0 / 0 / 0 |
| 95 | `tripar_1` | Tri Par 1 | Elation Opti Tri Par (as generic par) | Demo generic 12ch | 12 | 2 | 145 | Wall Pars | led_pars; wall_pars | -12.60 | 0.30 | -6.00 | 0 / 0 / 0 |
| 96 | `tripar_2` | Tri Par 2 | Elation Opti Tri Par (as generic par) | Demo generic 12ch | 12 | 2 | 157 | Wall Pars | led_pars; wall_pars | -12.60 | 0.30 | 0.00 | 0 / 0 / 0 |
| 97 | `tripar_3` | Tri Par 3 | Elation Opti Tri Par (as generic par) | Demo generic 12ch | 12 | 2 | 169 | Wall Pars | led_pars; wall_pars | -12.60 | 0.30 | 6.00 | 0 / 0 / 0 |
| 98 | `tripar_4` | Tri Par 4 | Elation Opti Tri Par (as generic par) | Demo generic 12ch | 12 | 2 | 181 | Wall Pars | led_pars; wall_pars | 12.60 | 0.30 | -6.00 | 0 / 0 / 0 |
| 99 | `tripar_5` | Tri Par 5 | Elation Opti Tri Par (as generic par) | Demo generic 12ch | 12 | 2 | 193 | Wall Pars | led_pars; wall_pars | 12.60 | 0.30 | 0.00 | 0 / 0 / 0 |
| 100 | `tripar_6` | Tri Par 6 | Elation Opti Tri Par (as generic par) | Demo generic 12ch | 12 | 2 | 205 | Wall Pars | led_pars; wall_pars | 12.60 | 0.30 | 6.00 | 0 / 0 / 0 |
| 101 | `tripar_7` | Tri Par 7 | Elation Opti Tri Par (as generic par) | Demo generic 12ch | 12 | 2 | 217 | Staircase Pars | led_pars; staircase_pars | -4.00 | 0.30 | 12.60 | 0 / 0 / 0 |
| 102 | `tripar_8` | Tri Par 8 | Elation Opti Tri Par (as generic par) | Demo generic 12ch | 12 | 2 | 229 | Staircase Pars | led_pars; staircase_pars | 4.00 | 0.30 | 12.60 | 0 / 0 / 0 |
| 103 | `ledwall_c_r1c1` | LED Wall Centre R1 C1 | LED video wall (make and model not reported) (as generic bar) | Demo generic 12ch | 12 | 3 | 1 | LED Wall Centre | led_wall; led_wall_centre; dj_booth | -2.40 | 5.20 | -13.30 | 0 / 0 / 0 |
| 104 | `ledwall_c_r1c2` | LED Wall Centre R1 C2 | LED video wall (make and model not reported) (as generic bar) | Demo generic 12ch | 12 | 3 | 13 | LED Wall Centre | led_wall; led_wall_centre; dj_booth | -1.20 | 5.20 | -13.30 | 0 / 0 / 0 |
| 105 | `ledwall_c_r1c3` | LED Wall Centre R1 C3 | LED video wall (make and model not reported) (as generic bar) | Demo generic 12ch | 12 | 3 | 25 | LED Wall Centre | led_wall; led_wall_centre; dj_booth | 0.00 | 5.20 | -13.30 | 0 / 0 / 0 |
| 106 | `ledwall_c_r1c4` | LED Wall Centre R1 C4 | LED video wall (make and model not reported) (as generic bar) | Demo generic 12ch | 12 | 3 | 37 | LED Wall Centre | led_wall; led_wall_centre; dj_booth | 1.20 | 5.20 | -13.30 | 0 / 0 / 0 |
| 107 | `ledwall_c_r1c5` | LED Wall Centre R1 C5 | LED video wall (make and model not reported) (as generic bar) | Demo generic 12ch | 12 | 3 | 49 | LED Wall Centre | led_wall; led_wall_centre; dj_booth | 2.40 | 5.20 | -13.30 | 0 / 0 / 0 |
| 108 | `ledwall_c_r2c1` | LED Wall Centre R2 C1 | LED video wall (make and model not reported) (as generic bar) | Demo generic 12ch | 12 | 3 | 61 | LED Wall Centre | led_wall; led_wall_centre; dj_booth | -2.40 | 4.40 | -13.30 | 0 / 0 / 0 |
| 109 | `ledwall_c_r2c2` | LED Wall Centre R2 C2 | LED video wall (make and model not reported) (as generic bar) | Demo generic 12ch | 12 | 3 | 73 | LED Wall Centre | led_wall; led_wall_centre; dj_booth | -1.20 | 4.40 | -13.30 | 0 / 0 / 0 |
| 110 | `ledwall_c_r2c3` | LED Wall Centre R2 C3 | LED video wall (make and model not reported) (as generic bar) | Demo generic 12ch | 12 | 3 | 85 | LED Wall Centre | led_wall; led_wall_centre; dj_booth | 0.00 | 4.40 | -13.30 | 0 / 0 / 0 |
| 111 | `ledwall_c_r2c4` | LED Wall Centre R2 C4 | LED video wall (make and model not reported) (as generic bar) | Demo generic 12ch | 12 | 3 | 97 | LED Wall Centre | led_wall; led_wall_centre; dj_booth | 1.20 | 4.40 | -13.30 | 0 / 0 / 0 |
| 112 | `ledwall_c_r2c5` | LED Wall Centre R2 C5 | LED video wall (make and model not reported) (as generic bar) | Demo generic 12ch | 12 | 3 | 109 | LED Wall Centre | led_wall; led_wall_centre; dj_booth | 2.40 | 4.40 | -13.30 | 0 / 0 / 0 |
| 113 | `ledwall_c_r3c1` | LED Wall Centre R3 C1 | LED video wall (make and model not reported) (as generic bar) | Demo generic 12ch | 12 | 3 | 121 | LED Wall Centre | led_wall; led_wall_centre; dj_booth | -2.40 | 3.60 | -13.30 | 0 / 0 / 0 |
| 114 | `ledwall_c_r3c2` | LED Wall Centre R3 C2 | LED video wall (make and model not reported) (as generic bar) | Demo generic 12ch | 12 | 3 | 133 | LED Wall Centre | led_wall; led_wall_centre; dj_booth | -1.20 | 3.60 | -13.30 | 0 / 0 / 0 |
| 115 | `ledwall_c_r3c3` | LED Wall Centre R3 C3 | LED video wall (make and model not reported) (as generic bar) | Demo generic 12ch | 12 | 3 | 145 | LED Wall Centre | led_wall; led_wall_centre; dj_booth | 0.00 | 3.60 | -13.30 | 0 / 0 / 0 |
| 116 | `ledwall_c_r3c4` | LED Wall Centre R3 C4 | LED video wall (make and model not reported) (as generic bar) | Demo generic 12ch | 12 | 3 | 157 | LED Wall Centre | led_wall; led_wall_centre; dj_booth | 1.20 | 3.60 | -13.30 | 0 / 0 / 0 |
| 117 | `ledwall_c_r3c5` | LED Wall Centre R3 C5 | LED video wall (make and model not reported) (as generic bar) | Demo generic 12ch | 12 | 3 | 169 | LED Wall Centre | led_wall; led_wall_centre; dj_booth | 2.40 | 3.60 | -13.30 | 0 / 0 / 0 |
| 118 | `ledwall_w_r1c1` | LED Wall Wing R1 C1 | LED video wall (make and model not reported) (as generic bar) | Demo generic 12ch | 12 | 3 | 181 | LED Wall Wings | led_wall; led_wall_wings; dj_booth | -5.50 | 5.20 | -13.30 | 0 / 0 / 0 |
| 119 | `ledwall_w_r1c2` | LED Wall Wing R1 C2 | LED video wall (make and model not reported) (as generic bar) | Demo generic 12ch | 12 | 3 | 193 | LED Wall Wings | led_wall; led_wall_wings; dj_booth | -4.50 | 5.20 | -13.30 | 0 / 0 / 0 |
| 120 | `ledwall_w_r1c3` | LED Wall Wing R1 C3 | LED video wall (make and model not reported) (as generic bar) | Demo generic 12ch | 12 | 3 | 205 | LED Wall Wings | led_wall; led_wall_wings; dj_booth | 4.50 | 5.20 | -13.30 | 0 / 0 / 0 |
| 121 | `ledwall_w_r1c4` | LED Wall Wing R1 C4 | LED video wall (make and model not reported) (as generic bar) | Demo generic 12ch | 12 | 3 | 217 | LED Wall Wings | led_wall; led_wall_wings; dj_booth | 5.50 | 5.20 | -13.30 | 0 / 0 / 0 |
| 122 | `ledwall_w_r2c1` | LED Wall Wing R2 C1 | LED video wall (make and model not reported) (as generic bar) | Demo generic 12ch | 12 | 3 | 229 | LED Wall Wings | led_wall; led_wall_wings; dj_booth | -5.50 | 4.40 | -13.30 | 0 / 0 / 0 |
| 123 | `ledwall_w_r2c2` | LED Wall Wing R2 C2 | LED video wall (make and model not reported) (as generic bar) | Demo generic 12ch | 12 | 3 | 241 | LED Wall Wings | led_wall; led_wall_wings; dj_booth | -4.50 | 4.40 | -13.30 | 0 / 0 / 0 |
| 124 | `ledwall_w_r2c3` | LED Wall Wing R2 C3 | LED video wall (make and model not reported) (as generic bar) | Demo generic 12ch | 12 | 3 | 253 | LED Wall Wings | led_wall; led_wall_wings; dj_booth | 4.50 | 4.40 | -13.30 | 0 / 0 / 0 |
| 125 | `ledwall_w_r2c4` | LED Wall Wing R2 C4 | LED video wall (make and model not reported) (as generic bar) | Demo generic 12ch | 12 | 3 | 265 | LED Wall Wings | led_wall; led_wall_wings; dj_booth | 5.50 | 4.40 | -13.30 | 0 / 0 / 0 |
| 126 | `ledwall_w_r3c1` | LED Wall Wing R3 C1 | LED video wall (make and model not reported) (as generic bar) | Demo generic 12ch | 12 | 3 | 277 | LED Wall Wings | led_wall; led_wall_wings; dj_booth | -5.50 | 3.60 | -13.30 | 0 / 0 / 0 |
| 127 | `ledwall_w_r3c2` | LED Wall Wing R3 C2 | LED video wall (make and model not reported) (as generic bar) | Demo generic 12ch | 12 | 3 | 289 | LED Wall Wings | led_wall; led_wall_wings; dj_booth | -4.50 | 3.60 | -13.30 | 0 / 0 / 0 |
| 128 | `ledwall_w_r3c3` | LED Wall Wing R3 C3 | LED video wall (make and model not reported) (as generic bar) | Demo generic 12ch | 12 | 3 | 301 | LED Wall Wings | led_wall; led_wall_wings; dj_booth | 4.50 | 3.60 | -13.30 | 0 / 0 / 0 |
| 129 | `ledwall_w_r3c4` | LED Wall Wing R3 C4 | LED video wall (make and model not reported) (as generic bar) | Demo generic 12ch | 12 | 3 | 313 | LED Wall Wings | led_wall; led_wall_wings; dj_booth | 5.50 | 3.60 | -13.30 | 0 / 0 / 0 |
| 130 | `booth_wash_1` | Booth Wash 1 | Elation Opti Tri Par (as generic par) | Demo generic 12ch | 12 | 3 | 325 | Booth Wash | led_pars; booth_wash; dj_booth | -3.50 | 6.00 | -13.30 | 0 / 0 / 0 |
| 131 | `booth_wash_2` | Booth Wash 2 | Elation Opti Tri Par (as generic par) | Demo generic 12ch | 12 | 3 | 337 | Booth Wash | led_pars; booth_wash; dj_booth | 3.50 | 6.00 | -13.30 | 0 / 0 / 0 |
