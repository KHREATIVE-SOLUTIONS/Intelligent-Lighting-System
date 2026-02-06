# Professional Concert Lighting - Training Video Catalog

> Training data catalog for the video-to-DMX ML pipeline.
> Last updated: 2026-02-06

---

## Table of Contents

1. [Purpose and Selection Criteria](#1-purpose-and-selection-criteria)
2. [Technical Requirements for Training Videos](#2-technical-requirements-for-training-videos)
3. [EDM / Electronic](#3-edm--electronic)
4. [Rock / Metal](#4-rock--metal)
5. [Pop](#5-pop)
6. [Hip-Hop / Rap](#6-hip-hop--rap)
7. [Nightclubs and Venues](#7-nightclubs-and-venues)
8. [Festival Mainstages](#8-festival-mainstages)
9. [Famous Lighting Designers](#9-famous-lighting-designers)
10. [YouTube Channels and Educational Resources](#10-youtube-channels-and-educational-resources)
11. [Industry Publications](#11-industry-publications)
12. [Console Programming Resources](#12-console-programming-resources)
13. [Training Data Diversity Matrix](#13-training-data-diversity-matrix)

---

## 1. Purpose and Selection Criteria

This catalog identifies professional concert lighting videos suitable for training our
video-to-DMX ML models (see `VIDEO_TO_DMX_TRAINING_PIPELINE.md`). Selected videos
will be processed through the Abstract Lighting Description (ALD) annotation pipeline
to create labeled training data mapping visual lighting states to DMX parameter values.

### Selection Priorities

- **Multi-camera professional recordings** with wide shots showing full rig behaviour
- **Known lighting designers** (so we can attribute style and verify techniques)
- **Genre diversity** to ensure the model generalises across musical styles
- **Technical quality** sufficient for frame-by-frame analysis
- **Variety of lighting techniques**: beam patterns, colour washes, strobes, chases,
  movement patterns, crowd lighting, performer key lighting

---

## 2. Technical Requirements for Training Videos

### Minimum Specifications

| Parameter | Minimum | Preferred |
|-----------|---------|-----------|
| Resolution | 1080p (1920x1080) | 4K (3840x2160) |
| Frame Rate | 30 fps | 60 fps |
| Bitrate | 8 Mbps | 20+ Mbps |
| Duration | 5 minutes (per clip) | Full set (30-180 min) |
| Audio | Stereo mix synced | Multichannel or board feed |

### Camera Angle Requirements

- **Wide shots (essential)**: Full stage visible, showing complete rig geometry,
  beam positions, and audience wash. Critical for fixture state estimation.
- **Medium shots (valuable)**: Stage-level showing fixture types, gobo patterns,
  and colour mixing detail.
- **Close-ups (supplementary)**: Individual fixture behaviour, DMX fade rates,
  colour temperature shifts. Useful for fine-grained parameter estimation.
- **Audience POV (valuable)**: What the audience actually sees; useful for
  validating that model output creates the intended visual impression.
- **Overhead/drone (supplementary)**: Spatial coverage patterns, zone mapping.

### What Disqualifies a Video

- Phone-cam recordings with excessive shake or compression artefacts
- Single fixed camera with no wide shots
- Heavy post-production colour grading that distorts actual lighting colours
- Videos where audience phones/screens dominate the frame
- Clips shorter than 30 seconds with no musical context

### Frame Extraction Strategy

For ML training, extract frames at **5 fps** for general state estimation (reduces
redundancy while capturing most transitions). Increase to **30 fps** during detected
transitions (strobe sequences, colour chases, blackouts) for fine-grained temporal
modelling. Audio features should be extracted at full sample rate and aligned to
video frames.

---

## 3. EDM / Electronic

### 3.1 Eric Prydz - EPIC / HOLOSPHERE

| Field | Detail |
|-------|--------|
| **Event** | EPIC 6.0 Holosphere (Tomorrowland debut, then touring) |
| **Lighting Design** | Ross Chapple (RCLD) - LD, Co-Designer, Operator |
| **Production Design** | Liam Tomaszewski (Punkette), Mark Calvert & Dave Green (RES), Bryn Williams (Light Initiative) |
| **Key Techniques** | 806,000 LED pixels on 8m sphere (16mm pitch, 64% transparency), 500+ controllable fixtures, automated spokes radiating from sphere, LED moving heads behind upstage wall interacting with content |
| **Genre** | Progressive House / Trance |
| **Training Value** | Exceptional: demonstrates large-scale LED integration, content-reactive lighting, volumetric effects inside transparent structure. The 2025 Holosphere 2.0 uses curved double-sided transparent LED panels never used elsewhere. |
| **Search Terms** | "Eric Prydz EPIC 6.0 Holosphere full set", "Eric Prydz Tomorrowland HOLOSPHERE" |
| **Sources** | [RES Project Page](https://www.resgb.com/epic-50-project), [LSI Online](https://www.lsionline.com/epic-holosphere-created-for-eric-prydz), [Billboard](https://www.billboard.com/music/music-news/eric-prydz-holosphere-tour-ibiza-unvrs-sphere-show-1236022201/) |

### 3.2 Swedish House Mafia

| Field | Detail |
|-------|--------|
| **Event** | Paradise Again Tour / Tomorrowland / Ushuaia Ibiza residency |
| **Lighting Design** | Production team TBC (specialised tour crew) |
| **Key Techniques** | Minimalist monochrome palette, heavy use of strobes and haze, sharp beam patterns, aggressive timing synced to drops |
| **Genre** | Progressive House / EDM |
| **Training Value** | High-energy EDM lighting with clean geometric looks. Their trademark is using few colours at once (often pure white or single saturated colour) with precise timing. |
| **Search Terms** | "Swedish House Mafia Paradise Again tour full set", "Swedish House Mafia Tomorrowland 2023 full set" |

### 3.3 Martin Garrix

| Field | Detail |
|-------|--------|
| **Event** | Red Rocks Takeover (Oct 2025), IDEM at RAI Amsterdam (2023), San Francisco 2024 |
| **Lighting Design** | Tour lighting team (138 Robe moving lights on SF show including Spikies, Pointes, BMFL Spots) |
| **Key Techniques** | Dedicated video clips and lighting looks per song (rock/pop approach to EDM), drone coverage, elaborate multi-layer beam shows |
| **Genre** | Big Room / Progressive House |
| **Training Value** | Demonstrates per-song lighting design approach in EDM context. The San Francisco production specifically treated each song as a unique visual chapter. |
| **Search Terms** | "Martin Garrix IDEM full set RAI Amsterdam", "Martin Garrix Red Rocks 2025 full set" |
| **Sources** | [EDM.com - IDEM](https://edm.com/news/watch-martin-garrix-3-hour-idem-dj-set-ade-2023/), [EDM.com - Red Rocks](https://edm.com/events/what-you-missed-martin-garrix-red-rocks-2025/) |

### 3.4 Deadmau5 - Cube V3

| Field | Detail |
|-------|--------|
| **Event** | Cube V3 Tour (2019-2025, retired Oct 2025) |
| **Production Design** | Chris Schroeder Productions, technical design by Collyns Stenzel |
| **Key Techniques** | 21ft tall, 22ft wide three-sided cube with LED panels, real-time audio-reactive content, 360-degree rotation, 90-to-45 degree tilt. Martin MAC Viper for hard edge, Ayrton MagicPanel 602 as pixel fixtures. |
| **Genre** | Progressive House / Electro |
| **Training Value** | Excellent for geometric structure lighting, audio-reactive visuals, and understanding how fixture placement on moving structures creates dynamic patterns. |
| **Search Terms** | "Deadmau5 Cube V3 full set", "Deadmau5 Cube V3 tour live" |
| **Sources** | [PLSN - Cube V3](https://plsn.com/articles/designer-insights/deadmau5-cube-v3-tour/), [Core Magazines](https://coremagazines.com/music/inside-giant-deadmau5-cube-stage-set/) |

### 3.5 Skrillex / Fred Again / Four Tet - MSG Rave

| Field | Detail |
|-------|--------|
| **Event** | Madison Square Garden, Feb 18, 2023 (sold out in 2 minutes) |
| **Lighting Design** | Ed Warren (Next Level Lights) |
| **Console** | ChamSys MagicQ MQ500 |
| **Key Techniques** | Entirely improvised (no timecode), translating music feel into light in real time. Rainbow lasers, cell-phone crowd engagement, warm walk-in transitioning to high-energy rave. Christie Lites rig plus MSG house rig. |
| **Genre** | Bass Music / UK Garage / House |
| **Training Value** | Exceptional example of fully improvised lighting that perfectly matches music energy. Demonstrates what "musical" lighting looks like without pre-programming. Invaluable for training models on energy-to-light mapping. |
| **Search Terms** | "Skrillex Fred Again Four Tet MSG full set", "Skrillex Madison Square Garden rave" |
| **Sources** | [EDM.com Interview](https://edm.com/interviews/skrillex-fred-again-four-tet-msg-rave-how-ed-warren-designed-lighting-lasers/), [ChamSys](https://uk.chamsyslighting.com/ed-warren-powers-four-tet-fred-again-and-skrillex-s-seminal-madison-square-garden-show-with-chamsys/), [PLSN](https://plsn.com/featured/ed-warren-powers-four-tet-fred-again-and-skrillexs-seminal-madison-square-garden-show-with-chamsys/) |

### 3.6 Dom Dolla & John Summit ("Everything Always")

| Field | Detail |
|-------|--------|
| **Event** | Ultra Music Festival 2025, Mainstage (Mar 28, 2025) |
| **Key Techniques** | High-energy b2b set with tech house / DnB hybrid, large festival mainstage LED + beam show |
| **Genre** | Tech House / DnB |
| **Training Value** | Full set available on YouTube. Festival mainstage context with genre-blending energy shifts - useful for training genre-transition detection. |
| **Search Terms** | "Dom Dolla John Summit Ultra Music Festival 2025 full set" |
| **Sources** | [Rolling Stone AU](https://au.rollingstone.com/music/music-news/dom-dollas-ultra-music-festival-2025-74903/) |

### 3.7 Illenium - Trilogy / Stadium Shows

| Field | Detail |
|-------|--------|
| **Event** | Trilogy at Allegiant Stadium, Las Vegas |
| **Lighting Design** | Chuck Williams |
| **Console** | MA Lighting grandMA3 |
| **Key Techniques** | 100+ GLP fixtures, four-hour three-set show with distinct lighting chapters per era (Ashes, Awake, Ascend). Emotional melodic bass with cinematic lighting transitions. |
| **Genre** | Melodic Bass / Future Bass |
| **Training Value** | Demonstrates emotional arc lighting over extended duration. Each era has distinct colour palettes and energy profiles - ideal for training mood-to-lighting mapping. |
| **Search Terms** | "Illenium Trilogy Allegiant Stadium full show", "Illenium live Las Vegas stadium" |
| **Sources** | [Live Design - grandMA3](https://www.livedesignonline.com/lighting/illenium-s-trilogy-concert-opens-allegiant-stadium-las-vegas-supported-by-grandma3), [Live Design - GLP](https://www.livedesignonline.com/news/over-100-glp-fixtures-light-up-illenium-stadium-show-las-vegas) |

### 3.8 Rufus Du Sol - Solace Tour

| Field | Detail |
|-------|--------|
| **Event** | Solace Live Tour |
| **Lighting Design** | Matthew Smith |
| **Key Techniques** | Minimalist approach, fixtures behind large video wall for depth, narrative-driven lighting journey matching song emotion. Ambient and atmospheric rather than aggressive. |
| **Genre** | Alternative Dance / Electronica |
| **Training Value** | Excellent counterpoint to aggressive EDM lighting. Shows how minimalism and restraint create emotional impact. Important for training the model to NOT over-light quiet passages. |
| **Search Terms** | "Rufus Du Sol Solace tour full set", "Rufus Du Sol live concert" |
| **Sources** | [Live Design - Solace Tour](https://www.livedesignonline.com/concerts/rufus-du-sol-s-solace-tour) |

### 3.9 Fisher

| Field | Detail |
|-------|--------|
| **Event** | Tomorrowland 2024/2025 Mainstage, Ultra Music Festival, various festival headlining sets |
| **Key Techniques** | High-energy festival house with aggressive strobe work, heavy CO2/pyro integration, crowd-facing beam arrays. Fisher's sets rely on festival infrastructure rather than bespoke touring rigs, making them excellent reference for how house music interacts with generic festival production. |
| **Genre** | Tech House / Fisher House |
| **Training Value** | Valuable as baseline festival EDM data - shows how a DJ without bespoke production utilises festival mainstage rigs. Useful for training the model on "standard festival" lighting as opposed to bespoke touring looks. |
| **Search Terms** | "Fisher Tomorrowland 2025 mainstage full set", "Fisher Ultra Music Festival full set" |

### 3.10 Tiesto

| Field | Detail |
|-------|--------|
| **Event** | Northern Lights Tour, European Summer Tours, Ushuaia Ibiza residency, F1 events |
| **Production** | Visual Endeavors (production design 2016-2018), Unlimited Productions (technical production) |
| **Key Techniques** | Large-scale LED walls, laser arrays, pyrotechnics, and immersive lighting. Tiesto's production emphasises spectacle and scale with saturated colour palettes and aggressive beam shows. Known for adapting production to diverse venue types (arena, festival, residency, F1 after-party). |
| **Genre** | Trance / Progressive House / EDM |
| **Training Value** | One of the longest-running EDM headliners with 25+ years of evolution in production design. Valuable for studying how EDM production has scaled over time. Ushuaia residency footage provides outdoor club-scale reference distinct from arena and festival. |
| **Search Terms** | "Tiesto live full set 2024", "Tiesto Ushuaia Ibiza full set", "Tiesto Tomorrowland full set" |
| **Sources** | [Visual Endeavors](https://visualendeavors.com/tiesto-tour/), [Unlimited Productions](https://unlimited-productions.com/cases/project/tiesto-summer-tour-2024/) |

### 3.11 John Summit

| Field | Detail |
|-------|--------|
| **Event** | Tomorrowland 2024 (Crystal Garden) / 2025 (Freedom Stage), Ultra Music Festival, "Everything Always" with Dom Dolla |
| **Key Techniques** | Tech house energy with festival-scale production, high BPM transitions, heavy strobe and laser usage. Summit represents the current generation of EDM headliners who have rapidly scaled from club to mainstage. |
| **Genre** | Tech House / House |
| **Training Value** | Represents current-generation EDM aesthetics. His rapid rise means production design is evolving across tours. The "Everything Always" b2b with Dom Dolla provides genre-blending reference. Closing Ultra 2026 mainstage signals peak-tier production access. |
| **Search Terms** | "John Summit Tomorrowland 2025 full set", "John Summit Ultra Music Festival full set" |

---

## 4. Rock / Metal

### 4.1 Rammstein - Stadium Tour

| Field | Detail |
|-------|--------|
| **Event** | World Stadium Tour (2019-2024, 135 shows, 6M spectators) |
| **Lighting Design** | Roland Greil & Patrick Woodroffe (Woodroffe-Bassett Design) |
| **Production Design** | Florian Wieder |
| **Key Techniques** | 122 Vari-Lite VL6000 Beams (104 upstage wall, 4 in pods, 14 under-stage shooting through grilled deck), massive pyrotechnics choreographed to music, Till Lindemann performing in flames (licensed pyrotechnician). Upstage wall reveal mid-show completely transforms scenery. |
| **Genre** | Industrial Metal / NDH |
| **Training Value** | Exceptional for pyro-lighting integration, dramatic reveals, and industrial aesthetics. The scale is unmatched. Behind-the-scenes documentary (Dec 2024) covers 90-truck, 1,350-tonne production across borders. |
| **Search Terms** | "Rammstein stadium tour full show", "Rammstein live concert 4K", "Rammstein behind the scenes documentary 2024" |
| **Sources** | [Vari-Lite](https://www.vari-lite.com/global/news/touring/rammstein), [Live Design](https://www.livedesignonline.com/special-report/rammstein-tour-motion), [Revolver Mag - Documentary](https://www.revolvermag.com/news/go-behind-the-scenes-of-rammsteins-world-stadium-tour-with-new-hour-long-documentary/) |

### 4.2 Metallica - M72 World Tour

| Field | Detail |
|-------|--------|
| **Event** | M72 World Tour (2023-2024) |
| **Lighting Design** | Rob Koenig (with Metallica since 2008) |
| **Key Techniques** | 600+ automated lights, in-the-round circular stage with "snake pit", Elation Proteus Excalibur sky beams, 144 Chauvet Color Strike M strobe washes, 48 Claypaky Sharpy Plus Aqua IP66 fixtures. Theatre-like interstitial moments with video and teasing light between songs. |
| **Genre** | Thrash Metal / Heavy Metal |
| **Training Value** | In-the-round staging provides unique 360-degree lighting perspective. The "theatre aspect" approach shows how rock lighting can be both aggressive and narrative. Two-night no-repeat format means varied cue lists for same songs. |
| **Search Terms** | "Metallica M72 full show", "Metallica M72 World Tour live 4K" |
| **Sources** | [Live Design - Proteus](https://www.livedesignonline.com/news/rob-koenig-lights-metallica-m72-world-tour-proteus), [PLSN - M72](https://plsn.com/articles/production-spotlight/metallica-m72-world-tour/), [PLSN - Color Strike](https://plsn.com/featured/rob-koenig-powers-metallica-m72-world-tour-looks-with-chauvet-professional-color-strike-m/) |

### 4.3 Tool

| Field | Detail |
|-------|--------|
| **Event** | Tool touring productions (2019-2024) |
| **Lighting Design** | Mark "Junior" Jacobson (lighting), Breckinridge Haggerty (video), Scott Wilson (lasers) |
| **Console** | MA Lighting grandMA consoles |
| **Key Techniques** | 56x28ft white marley floor as projection surface, 12 Christie S+16K DLP projectors, minimalist colour build from start to overload by end. All cues fired manually (no click track) - video and lighting operators match band timing in real time. Adam Jones deeply involved in visual direction. |
| **Genre** | Progressive Metal / Art Rock |
| **Training Value** | Demonstrates projection-as-lighting, manual timing without click, and progressive intensity build over a full set. Invaluable for teaching the model about gradual energy escalation. |
| **Search Terms** | "Tool live concert full show 4K", "Tool Fear Inoculum tour visual production" |
| **Sources** | [Live Design](https://www.livedesignonline.com/concerts/tool-time) |

### 4.4 Muse - Will of the People Tour

| Field | Detail |
|-------|--------|
| **Event** | Will of the People World Tour (Jan-Jul 2023) |
| **Creative Direction** | Jesse Lee Stout (Metaform Studio) |
| **Lighting Design** | Sooner Routhier; Associate LD Aaron Luke (Luminescence) |
| **Key Techniques** | 75% plexiglass stage exposing gear below, overhead rig duplicated under stage for taller beams through floor, 15ft animated flaming logo, 30ft+ inflatables with plexiglass mirror masks bouncing light, kinetic ceiling mirrors, homogeneous fixture selection for unified vocabulary. Post-apocalyptic industrial aesthetic. |
| **Genre** | Alternative Rock / Space Rock |
| **Training Value** | Outstanding for reflective surface lighting, under-stage uplight techniques, and creating atmosphere through industrial minimalism. Mirror-bounce effects are technically challenging and excellent training data for understanding reflected light paths. |
| **Search Terms** | "Muse Will of the People tour full concert", "Muse live 2023 full show" |
| **Sources** | [PLSN](https://plsn.com/articles/design-spotlight/muse-will-of-the-people-world-tour/), [Sooner Rae Creative](https://soonerrae.com/muse-will-of-the-people), [FOH Magazine](https://fohonline.com/articles/production-profile/muse-will-of-the-people-world-tour-2023/) |

---

## 5. Pop

### 5.1 Taylor Swift - The Eras Tour

| Field | Detail |
|-------|--------|
| **Event** | The Eras Tour (2023-2024, highest-grossing tour in history) |
| **Show Director / Lighting Design** | Baz Halpin |
| **Production** | PRG (lighting company), Silent House (production) |
| **Key Techniques** | Multi-era visual storytelling (each album has distinct colour palette and lighting language), massive LED screens, wristband crowd lighting, kinetic set pieces, timed confetti and pyro. Shifts from intimate acoustic to stadium spectacle within single show. |
| **Genre** | Pop |
| **Training Value** | Gold standard for narrative lighting across genre shifts within one performance. Each era demonstrates different design philosophies (country warmth, pop brightness, indie moodiness, synth-wave neon). Essential for training genre-adaptive models. |
| **Search Terms** | "Taylor Swift Eras Tour full concert 4K", "Taylor Swift Eras Tour film" |
| **Sources** | [TAIT](https://www.taittowers.com/work/taylor-swift-reputation-world-tour), [Chauvet - Baz Halpin](https://www.chauvetprofessional.com/news/baz-halpin-evolving-light/) |

### 5.2 Beyonce - Renaissance World Tour

| Field | Detail |
|-------|--------|
| **Event** | Renaissance World Tour (May-Oct 2023, 56 shows) |
| **Lighting Design** | Tobias Rylander |
| **Stage Design** | Es Devlin Studio + Stufish Entertainment Architects |
| **Automation** | TAIT Navigator Automation Platform |
| **Key Techniques** | 15m high video facade with circular aperture "portal", chrome-filled immersive environment, dual-stage connected by ramp, 137ft diameter runway with Club Renaissance underneath, robotic arms, UV technology, mechanical lifts and treadmills, flying 3D rigs. Six-act three-hour structure with distinct lighting worlds (disco cowboy, hypnotic red universe, intergalactic chrome). |
| **Genre** | Pop / R&B / Dance |
| **Training Value** | Exceptional for act-based lighting transitions, portal/reveal techniques, and UV integration. The six distinct visual worlds within one show provide diverse training data from a single source. |
| **Search Terms** | "Beyonce Renaissance World Tour full concert", "Beyonce Renaissance tour film" |
| **Sources** | [Stufish](https://stufish.com/project/beyonce/), [TAIT](https://www.taittowers.com/work/beyonce-renaissance-world-tour), [Green Wall Designs](https://greenwall.se/all/beyonce-renaissance-world-tour/) |

### 5.3 Coldplay - Music of the Spheres World Tour

| Field | Detail |
|-------|--------|
| **Event** | Music of the Spheres World Tour (2022-2025) |
| **Production Design** | Misty Buckley (co-creative director with Phil Harvey) |
| **Lighting Design** | Sooner Routhier |
| **Wristband Control** | Shaheem Litchmore (PixMob programmer + lighting operator) |
| **Key Techniques** | ~600 colour fixtures (IP65 rated for outdoor weather resistance), PixMob sugarcane wristbands with LEDs and IR transmitters turning crowd into part of show, space-themed colour palette, Ayrton fixtures. 85% wristband return rate via collection program. |
| **Genre** | Alternative Rock / Pop |
| **Training Value** | Critical for crowd-as-lighting-element training data. The PixMob wristband system means the audience IS part of the light show - essential for teaching models about venue-wide illumination beyond stage fixtures. Also demonstrates eco-conscious production design. |
| **Search Terms** | "Coldplay Music of the Spheres full concert 4K", "Coldplay live PixMob wristbands" |
| **Sources** | [PLSN](https://plsn.com/archives/august-2022/coldplay-music-of-the-spheres-tour/), [Ayrton/PLSN](https://plsn.com/featured/ayrton-lights-coldplays-stadium-leg-of-music-of-the-spheres-world-tour/), [Exposed Magazine](https://www.exposedmagazine.co.uk/featured-articles/behind-the-lights-the-geniuses-powering-coldplays-immersive-music-of-the-spheres-world-tour/) |

### 5.4 The Weeknd - After Hours Til Dawn Tour

| Field | Detail |
|-------|--------|
| **Event** | After Hours Til Dawn Tour (2022-2023, stadiums worldwide) |
| **Lighting Design** | Jason Baeri |
| **Production Design** | Es Devlin |
| **Scenic Design** | Jason Ardizzone-West |
| **Key Techniques** | 450+ Elation Proteus Hybrid/Excalibur moving heads, 1,100+ total fixtures, 180ft wide LED wall, 30ft diameter moon set piece, dystopian chrome cityscape scenery. 2023 legs reimagined with crumbling post-apocalyptic chrome buildings replacing LED skyline. Gotham-style motifs with smoke and dramatic lighting. Open-air adjustments widened sight-lines and intensified backlight. |
| **Genre** | R&B / Pop / Dark Wave |
| **Training Value** | Exceptional for dystopian/cinematic lighting aesthetics and how the same tour evolves across legs (LED skyline vs. chrome cityscape). The 180ft LED wall provides massive content-reactive lighting training data. Moon set piece creates focal point lighting. |
| **Search Terms** | "The Weeknd After Hours Til Dawn full concert", "The Weeknd stadium tour 4K" |
| **Sources** | [JAWSTUDIO](https://www.jawstudiony.com/tv-film-concerts/the-weeknd-after-hours-til-dawn-set-design-producer), [Live Design](https://www.livedesignonline.com/news/over-450-proteus-workhorses-light-weeknd-after-hours-til-dawn-stadium-tour), [TAIT](https://www.taittowers.com/work/after-hours-til-dawn-tour) |

### 5.5 Bruno Mars - 24K Magic World Tour

| Field | Detail |
|-------|--------|
| **Event** | 24K Magic World Tour (2017-2018, 114 shows) |
| **Production / Lighting Design** | LeRoy Bennett (production), Cory FitzGerald (lead LD), Whitney Hoversten (lighting director/programmer) |
| **Lighting Supply** | VER |
| **Key Techniques** | Record-setting 795 Robe Spikies on 20 moving over-stage pods, 48 Vari-Lite VL6000 Beams on vertical truss, 53 VL4000 BeamWash for backlight/sidelight, 214 TMB Flares. Retro-modern design mixing classic Par Can aesthetics with high-power moving lights. '70s funk/soul meets '90s era visual vocabulary with contemporary execution. |
| **Genre** | Pop / Funk / R&B |
| **Training Value** | Outstanding for retro-modern lighting aesthetic study. The Par Can + moving light hybrid approach demonstrates how fixture selection creates visual era. The 795 identical Spikies on moving pods show what massive fixture counts of a single type can achieve. LeRoy Bennett's design philosophy is directly observable. |
| **Search Terms** | "Bruno Mars 24K Magic tour full concert", "Bruno Mars live concert 4K" |
| **Sources** | [PLSN](https://plsn.com/articles/wide-focus/bruno-mars-24k-magic-world-tour/), [SACO](https://saco.com/bruno-mars-24k-magic-tour/), [LeRoy Bennett](https://www.leroybennett.com/post/24k-magic), [Vari-Lite](https://www.vari-lite.com/global/news/touring/bruno-mars) |

---

## 6. Hip-Hop / Rap

### 6.1 Drake - It's All A Blur Tour

| Field | Detail |
|-------|--------|
| **Event** | It's All A Blur Tour / Big As the What? (2023-2024, 82 dates North America) |
| **Lighting Design** | John Torres |
| **Creative Direction** | TAWBOX (London) |
| **Visuals** | Luke Halls Studio |
| **Key Techniques** | Monolithic centre stage as architectural light canvas, 360-degree design, plexiglass floating floor, 30ft tall inflatables, robots, precisely timed lasers, three separate stages. Classical-meets-spectacle aesthetic. 14-person lighting crew led by Ronnie Beal (PRG). |
| **Genre** | Hip-Hop / R&B |
| **Training Value** | Demonstrates hip-hop's current high-production approach. Multiple stage transitions and the classical-vs-spectacle balance provide training data for restraint-to-explosion dynamics. |
| **Search Terms** | "Drake It's All A Blur tour full concert", "Drake concert 2024 4K" |
| **Sources** | [Luke Halls Studio](https://lukehalls.com/works/drake-its-all-a-blur-tour/), [Variety](https://variety.com/2023/music/news/drake-its-all-a-blur-tour-matte-babel-dreamcrew-1235703521/), [TAIT](https://www.taittowers.com/work/its-all-a-blur-tour) |

### 6.2 Kendrick Lamar - The Big Steppers Tour

| Field | Detail |
|-------|--------|
| **Event** | The Big Steppers Tour (2022-2024, 103 shows across 6 continents) |
| **Lighting Design / Creative Production** | Cory Fitzgerald |
| **Lighting Direction** | Marcus Jessup Jr. |
| **Key Techniques** | Minimalist all-white three-stage design (main + middle + mirror elevator), white curtain draping, square light panels descending from rafters hovering over performer, shadow play, puppetry, pyrotechnics, pale white colour palette referencing therapy themes. Cinematic live camera capture. |
| **Genre** | Hip-Hop / Conscious Rap |
| **Training Value** | Exceptional example of thematic/narrative lighting in hip-hop. The minimalist white palette with occasional colour shifts provides clean training data for understanding restraint and how single-colour choices create mood. Shadow play techniques are rare in concert lighting ML data. |
| **Search Terms** | "Kendrick Lamar Big Steppers tour full concert", "Kendrick Lamar live 2023" |
| **Sources** | [Mike Carson TV](https://www.mikecarson.tv/projects/kendrick-lamar-the-big-steppers-tour), [Variety](https://variety.com/2022/music/news/kendrick-lamar-big-steppers-tour-concert-review-1235334843/) |

### 6.3 Travis Scott - Circus Maximus / Utopia Tour

| Field | Detail |
|-------|--------|
| **Event** | Circus Maximus / Utopia Tour (2023-2024) |
| **Production** | Fuse (lighting/video/rigging), Strictly FX (lasers/pyro), CyberMotion (automation), Accurate Staging |
| **Key Techniques** | Easter Island-style stone head set pieces with lasers, CyberMotion lifts, arena-length stage, dystopian flying heads, giant boulders, heavy pyro, fever-dream scenic design. Immersive surround experience engaging all senses. |
| **Genre** | Hip-Hop / Trap |
| **Training Value** | Demonstrates theatrical set-piece-integrated lighting (heads with lasers, lit boulders) and how scenic elements become light sources. Heavy pyro integration with trap energy provides aggressive visual training data. |
| **Search Terms** | "Travis Scott Utopia Circus Maximus tour full show", "Travis Scott concert 2024 4K" |
| **Sources** | [RapTV](https://raptv.com/article/the-making-of-travis-scotts-stage-design-circus-maximus-tour/) |

### 6.4 Tyler, the Creator - Camp Flog Gnaw / IGOR / Chromakopia

| Field | Detail |
|-------|--------|
| **Event** | Camp Flog Gnaw Carnival (annually at Dodger Stadium), IGOR tour, Chromakopia era (2024-2025) |
| **Production** | Effixx Studio (Camp Flog Gnaw 2023) |
| **Key Techniques** | Bespoke stage design unique to each year/era (never reused on tour). 2024: junkyard aesthetic with crane, cars, flamethrower, single green light on masked figure atop shipping container. 2023: LA Metro station replica with entrance stairway. Choreographed lighting timed to interact with scenic foreground elements, creating theatrical depth. |
| **Genre** | Hip-Hop / Alternative Rap |
| **Training Value** | Demonstrates how thematic stage design drives lighting choices rather than vice versa. Each era has completely different visual language. The junkyard and metro station sets show how non-traditional scenic elements become lighting surfaces. Valuable for training models on theatrical/narrative hip-hop aesthetics. |
| **Search Terms** | "Tyler the Creator Camp Flog Gnaw 2024 full set", "Tyler the Creator Chromakopia live concert", "Tyler the Creator IGOR tour full show" |
| **Sources** | [Effixx Studio](https://www.effixx.studio/projects/tyler-cfg2023), [Billboard](https://www.billboard.com/music/rb-hip-hop/tyler-the-creator-2024-camp-flog-gnaw-headlining-performance-recap-1235831400/) |

---

## 7. Nightclubs and Venues

### 7.1 Hi Ibiza

| Field | Detail |
|-------|--------|
| **Venue** | Hi Ibiza (voted #1 Club in the World 2022-2025, DJ Mag) |
| **Lighting System** | Robe fixtures, highly customisable rigs that physically move around the Theatre room based on night's production requirements |
| **Spaces** | Theatre, Club Room, Wild Corner - each with independent visual installations |
| **Key Techniques** | Per-night reconfigurable fixture positioning, custom visual installations per residency (e.g., David Guetta Future Rave), mesmerising visual installations, cutting-edge sound integration |
| **Training Value** | Shows how the same venue adapts lighting for different genres/artists on different nights. Valuable for training models to understand venue-adaptive lighting vs. touring production. |
| **Search Terms** | "Hi Ibiza club night 4K", "Hi Ibiza David Guetta Future Rave", "Hi Ibiza Tale of Us Afterlife" |
| **Sources** | [Robe](https://www.robe.cz/news/robe-gets-hi-in-ibiza), [Kinetic Lights](https://www.kinetic-lights.com/project/mirror-mirror/hi-club-ibiza) |

### 7.2 Printworks London

| Field | Detail |
|-------|--------|
| **Venue** | Printworks London (converted industrial print works, DJ Mag #2 Club 2023) |
| **Lighting System** | Kinesys lighting rig, 12x4m LED screen, custom "blinder" capable of illuminating entire main room, 180+ metres of Sceptron LED strips |
| **Visual Design** | Rebel Overlay |
| **Key Techniques** | Industrial architecture as visual canvas, LED wall + lighting array for full-room colour sheets, strobing synchronisation, bespoke blinder effects. The massive industrial ceiling height allows for dramatic vertical beam shows. |
| **Training Value** | Industrial venue lighting differs fundamentally from arena/festival. The long narrow architecture creates unique beam geometry. Valuable for training models on venue-shape-adaptive lighting. |
| **Search Terms** | "Printworks London event 4K", "Printworks London DJ set full", "Printworks London lighting" |
| **Sources** | [DJ Mag](https://djmag.com/top100clubs/2023/2/Printworks-London) |

### 7.3 Fabric London

| Field | Detail |
|-------|--------|
| **Venue** | Fabric, London (opened 1999, legendary electronic music club) |
| **Design** | Dave Parry (sound and lighting engineer, designed entire club) |
| **Key Techniques** | Three rooms with independent systems, bodysonic vibrating dancefloor (400 bass transducers in Room 1), 3D-modelled sound allowing DJs to "move" sound across floor, stripped-back minimal lighting letting music dominate |
| **Training Value** | Represents the "less is more" nightclub philosophy where lighting serves the music rather than dominating. Valuable for training models on appropriate restraint in dark club environments. |
| **Search Terms** | "Fabric London live set", "Fabric London Room 1 DJ set" |
| **Sources** | [London Museum](https://www.londonmuseum.org.uk/collections/london-stories/fabric-a-nightclub-for-a-new-millennium/), [Vice - Dave Parry](https://www.vice.com/en/article/dave-parry-fabric-matter-ministry-of-sound-camden-palace-sound-lighting-engineer-designer/) |

### 7.4 Berghain, Berlin

| Field | Detail |
|-------|--------|
| **Venue** | Berghain, Berlin (converted power station, legendary techno club since 2004) |
| **Lighting Design** | Andre Jurgens |
| **Sound System** | Funktion-One (Dance Stack, upgraded 2023); Panorama Bar upgraded 2017 with Studt Akustik |
| **Key Techniques** | Deliberately minimal and precise lighting - Berghain main floor remains mostly dark to mirror intense techno, while Panorama Bar upstairs has more dynamic colourful scheme. No decorative elements; everything calculated to elevate the sound. Brutalist architecture provides the "set design" - concrete, steel, industrial space at massive scale. |
| **Training Value** | Essential for training the model on maximum restraint. Berghain proves that near-darkness with precise accent lighting can create as much impact as hundreds of fixtures. Critical for the model learning when NOT to add light. Dark techno and minimal techno require fundamentally different lighting approaches than other EDM subgenres. Note: photography is banned inside Berghain, so reference material is extremely limited but conceptually invaluable. |
| **Search Terms** | "Berghain Berlin interior lighting", "Berghain Panorama Bar atmosphere" |
| **Sources** | [D6W Studios](https://www.d6wstudios.com/blog/berghain-brutalism-counterculture-and-the-architecture-of-queer-nightlife), [visitBerlin](https://www.visitberlin.de/en/berghain-panorama-bar) |

### 7.5 Amnesia Ibiza

| Field | Detail |
|-------|--------|
| **Venue** | Amnesia Ibiza (opened 1970, one of Ibiza's oldest and most iconic clubs) |
| **Key Techniques** | Large LED screens for per-artist visual shows, lasers with geometric patterns, state-of-the-art holographic performance technology (new for 2024 blending physical and digital performances), Pyramid production with powerful sound and immersive lighting. Multiple dancefloors with independent production. |
| **Training Value** | Represents the high-end Ibiza superclub aesthetic. The 2024 holographic technology introduction provides forward-looking training data on emerging lighting techniques. The Pyramid production series brings touring-quality production into a club environment - useful for training models on the club-meets-festival production hybrid. |
| **Search Terms** | "Amnesia Ibiza Pyramid 4K", "Amnesia Ibiza DJ set full production" |
| **Sources** | [Amnesia Ibiza](https://www.amnesia.es/), [Mixmag](https://mixmag.net/read/pyramid-at-amnesia-reveals-weekly-2024-line-up-news) |

---

## 8. Festival Mainstages

### 8.1 Tomorrowland Mainstage (2024 "LIFE")

| Field | Detail |
|-------|--------|
| **Event** | Tomorrowland Belgium 2024 (400,000 attendees) |
| **Stage Specs** | 36m tall, 160m wide, 230 speakers/subs, 1,100 custom LED lights, 1,054 lamps |
| **Key Techniques** | 300+ LED laser moving heads for holographic volumetric effects, INFiLED ARmk2 LED (12,000:1 contrast, 5,000 nits brightness), NovaStar 5G signal transmission (world first), pyro-beam-LED screen integration |
| **Training Value** | The largest scale lighting production in the world. Essential training data for understanding massive open-air festival lighting where fixtures must compete with ambient daylight during golden hour sets and transition to night. |
| **Search Terms** | "Tomorrowland 2024 mainstage full set", "Tomorrowland LIFE stage 4K" |
| **Sources** | [EDM Identity](https://edmidentity.com/2024/07/19/tomorrowland-life-mainstage/), [INFiLED](https://www.infiled.com/projects/breathing-life-into-tomorrowland-2024-with-pixelscreen-and-infiled/) |

### 8.2 EDC Las Vegas (Electric Daisy Carnival)

| Field | Detail |
|-------|--------|
| **Event** | EDC Las Vegas 2024 (Las Vegas Motor Speedway, dusk-till-dawn) |
| **Lighting Design** | Steve Lieberman / SJ Lighting (15+ years designing EDC stages) |
| **Key Techniques** | Wasteland stage: 130+ Chauvet Color STRIKE M IP65 motorised strobe/wash fixtures, STRIKE Array 2C full-colour audience blinders. Multiple themed stages each with independent production design. Layout rearranged annually with new installations and art cars. Dusk-to-dawn operation means lighting must transition across ambient light conditions. |
| **Training Value** | EDC represents the pinnacle of US festival production. Steve Lieberman's long tenure means a consistent design philosophy across years, useful for studying evolution. The dusk-to-dawn format uniquely captures golden hour, sunset, full dark, and pre-dawn ambient transitions in a single event. Multiple stage designs within one festival provide diverse data. |
| **Search Terms** | "EDC Las Vegas 2024 full set mainstage", "EDC Las Vegas kineticFIELD 4K", "EDC Las Vegas Wasteland stage" |
| **Sources** | [Chauvet Professional](https://www.chauvetprofessional.com/steve-lieberman-paints-the-edc-las-vegas-2024-wasteland-stage-with-color-strike-m/) |

### 8.3 Creamfields UK

| Field | Detail |
|-------|--------|
| **Event** | Creamfields 2024, Daresbury UK |
| **Key Stages** | APEX (world's biggest indoor mainstage, 30,000 capacity), HALO (360-degree outdoor, 45m circular structure), Runway (55.2m x 4.2m ROE CB5 LED ceiling + 8 LED columns), Steel Yard, Arc Stage |
| **Production** | 4Wall Entertainment (Runway video package) |
| **Key Techniques** | Indoor mainstage provides weather-shielded immersive experience with controlled lighting environment. HALO's 360-degree structure with immersive lighting, video and sound. Runway's suspended LED ceiling over audience creates overhead canopy lighting effect. |
| **Training Value** | Valuable for comparing indoor vs. outdoor festival lighting within the same event. The APEX indoor mainstage provides controlled-environment festival data (like arena but at festival scale). HALO's 360-degree design provides surround-lighting training data similar to Metallica's in-the-round approach but at festival scale. |
| **Search Terms** | "Creamfields 2024 APEX stage full set", "Creamfields HALO stage 4K", "Creamfields Runway stage" |
| **Sources** | [4Wall Entertainment](https://europe.4wall.com/portfolio/entry/creamfields-2024), [We Rave You](https://weraveyou.com/2023/11/creamfields-apex-stage-2024/) |

---

## 9. Famous Lighting Designers

### 9.1 Baz Halpin

| Field | Detail |
|-------|--------|
| **Title** | Show Director / Lighting Designer |
| **Notable Clients** | Taylor Swift (Reputation, Eras Tour), Pink, multiple Super Bowl halftime shows |
| **Philosophy** | Serves as both creative producer and LD, treating concert lighting as theatrical storytelling. Evolves the visual language of light across tours. |
| **Techniques** | Multi-era visual narratives, stadium-scale intimacy, colour psychology per musical era |
| **Sources** | [Chauvet Professional](https://www.chauvetprofessional.com/news/baz-halpin-evolving-light/), [TAIT](https://www.taittowers.com/work/taylor-swift-reputation-world-tour) |

### 9.2 Patrick Woodroffe OBE RDI

| Field | Detail |
|-------|--------|
| **Title** | Lighting Designer / Director |
| **Career** | Active since 1973 (50+ years). Big break: Rod Stewart (hired day before tour). Rolling Stones LD since 1982 (longest-serving crew alongside Chuck Leavell). |
| **Notable Clients** | The Rolling Stones, Rammstein (with Woodroffe-Bassett Design), Rod Stewart, plus opera and ballet |
| **Awards** | 2022 LIT Lifetime Achievement Award |
| **Philosophy** | "See the bigger picture and work out what the director or performer needs." First to bring automated concert lights into opera/ballet. Embraces imperfection ("Their imperfection is their strength"). |
| **Techniques** | Cross-disciplinary approach (rock > opera > architecture), automated lighting in classical contexts, understanding that production authenticity matters more than technical perfection |
| **Sources** | [Spotlight Interview](https://spotlight.nu/features/interview-with-lighting-designer-patrick-woodroffe/), [LIT Awards](https://litawards.com/patrick-woodroffe-lifetime-achievement-awards-2022/), [Live Design](https://www.livedesignonline.com/news/patrick-woodroffe-and-politics-failure) |

### 9.3 LeRoy Bennett

| Field | Detail |
|-------|--------|
| **Title** | Production and Lighting Designer |
| **Company** | Seven Design Works (founded 2012) |
| **Career** | Started with 14-year run as Prince's collaborator. Five Super Bowl halftime shows. |
| **Notable Clients** | Prince, Paul McCartney, Madonna, Lady Gaga, Beyonce, Bruno Mars, Nine Inch Nails, Rammstein, The Weeknd, Ariana Grande, Keith Urban |
| **Philosophy** | Constant creative innovation. Never allows himself to become comfortable in his approach. Designs experiences, not just light shows. |
| **Techniques** | Multi-sensory production design, iconic set piece integration, cross-genre adaptability (Prince to NIN to Beyonce) |
| **Sources** | [LIT Awards Jury](https://litawards.com/jury/leroy-bennett/), [Variety](https://variety.com/2019/music/production/production-lighting-design-ariana-grande-lady-gaga-1203161848/), [LeRoy Bennett Website](https://www.leroybennett.com/) |

### 9.4 Scott Holthaus

| Field | Detail |
|-------|--------|
| **Title** | Lighting Designer / Director, Ayrton Lighting Designer Relations |
| **Company** | HappyMachine |
| **Career** | 35+ years in live entertainment. Started at Vari*Lite, dimmer tech for Pearl Jam, LD for Fleetwood Mac 2014-2015. UNLV theatre degree. |
| **Notable Clients** | Red Hot Chili Peppers, Pearl Jam, Foo Fighters, Blink 182, Motley Crue, Weezer, Kelly Clarkson, Disturbed, Alice In Chains |
| **Awards** | Parnelli Award nomination (LD of the Year), Pollstar nomination (Most Creative Stage Production for RHCP 2017) |
| **Philosophy** | "Clean, simple designs that adhere to the artist deliver the biggest visual impact." 1000+ fixture RHCP rig on moving truss. |
| **Techniques** | Moving truss integration, festival-specific design expertise (Coachella, Bonnaroo, SXSW), clean geometric looks |
| **Sources** | [Chauvet Professional](https://www.chauvetprofessional.com/news/scott-holthaus-moving-light/), [LinkedIn](https://www.linkedin.com/in/scott-holthaus-67226a108/), [HappyMachine](http://happymachine.net/) |

### 9.5 Chris Lose

| Field | Detail |
|-------|--------|
| **Title** | Lighting Director / Designer, Ayrton Designer Relations |
| **Base** | Las Vegas |
| **Career** | UNLV theatre degree, Crystal Cruises PM/LD, Pearl Jam dimmer tech, Fleetwood Mac LD, extensive festival circuit |
| **Philosophy** | "Clean, simple designs that adhere to the artist deliver the biggest visual impact." Invokes emotion through colour, atmosphere and beauty. Pragmatic problem-solving with mindfulness. |
| **Notable Expertise** | Festival lighting design best practices, published guidance in PLSN |
| **Sources** | [Q3 Las Vegas](https://q3lv.com/about-chris--2), [LD-at-Large Podcast](https://podcasts.apple.com/us/podcast/ld-at-large-podcast/id1465669474), [PLSN - Dear Festival LD](https://plsn.com/articles/ld-at-large/dear-festival-lighting-designer/) |

### 9.6 Ed Warren

| Field | Detail |
|-------|--------|
| **Title** | Lighting Designer |
| **Company** | Next Level Lights |
| **Notable Work** | Four Tet (long-term collaboration), Skrillex/Fred Again/Four Tet MSG rave |
| **Console** | ChamSys MagicQ MQ500 |
| **Philosophy** | Does not create a "light show" - translates the feel of music into light. Entirely improvised, no timecode. |
| **Techniques** | Real-time music-responsive operation, crowd engagement via cellphone lighting, warm-to-intense energy arcs |
| **Sources** | [EDM.com](https://edm.com/interviews/skrillex-fred-again-four-tet-msg-rave-how-ed-warren-designed-lighting-lasers/), [Next Level Lights](https://www.nextlevellights.com/four-tetfred-againskrillex-b2b) |

### 9.7 Rob Koenig

| Field | Detail |
|-------|--------|
| **Title** | Lighting Designer |
| **Notable Work** | Metallica (since 2008, four album cycles), M72 World Tour |
| **Equipment** | 600+ automated lights, Proteus Excalibur, Chauvet Color Strike M, Claypaky Sharpy Plus Aqua |
| **Philosophy** | Brings theatre aspects into rock, using interstitial lighting moments between songs for narrative progression. Fan of Metallica growing up - personal connection to the material. |
| **Sources** | [Live Design](https://www.livedesignonline.com/news/rob-koenig-lights-metallica-m72-world-tour-proteus), [PLSN](https://plsn.com/articles/production-spotlight/metallica-m72-world-tour/) |

### 9.8 Sooner Routhier

| Field | Detail |
|-------|--------|
| **Title** | Lighting Designer |
| **Company** | Sooner Rae Creative |
| **Notable Work** | Muse (Will of the People), Coldplay (Music of the Spheres) |
| **Techniques** | IP65-rated weather-resistant fixtures for outdoor shows, reflective surface lighting, under-stage rigs, homogeneous fixture selection for unified visual vocabulary |
| **Sources** | [Sooner Rae Creative](https://soonerrae.com/), [PLSN - Muse](https://plsn.com/articles/design-spotlight/muse-will-of-the-people-world-tour/) |

### 9.9 Additional Notable Designers

| Designer | Known For | Key Contribution |
|----------|-----------|------------------|
| **Tobias Rylander** | Beyonce Renaissance Tour | Portal/reveal techniques, UV integration |
| **Chuck Williams** | Illenium Trilogy | Emotional EDM, multi-era shows |
| **Ross Chapple (RCLD)** | Eric Prydz EPIC/Holosphere | LED sphere lighting, volumetric effects |
| **Mark "Junior" Jacobson** | Tool | Manual timing, projection-as-lighting |
| **Cory Fitzgerald** | Kendrick Lamar Big Steppers | Minimalist narrative hip-hop lighting |
| **Chris Kuroda** | Phish | Improvised jam band lighting (20+ years) |
| **Rob Sinclair** | Adele, LCD Soundsystem, David Byrne | Intimate + theatrical concert lighting |
| **Jason Baeri** | The Weeknd After Hours Til Dawn | Dystopian stadium lighting, 1,100+ fixture rigs |
| **Steve Lieberman (SJ Lighting)** | EDC Las Vegas (15+ years) | Festival-scale production design, multi-stage |
| **Whitney Hoversten** | Bruno Mars 24K Magic | Retro-modern lighting programming |
| **Andre Jurgens** | Berghain | Minimal precision club lighting |

---

## 10. YouTube Channels and Educational Resources

### Concert Lighting Focused

| Channel / Resource | Focus | Value for Training |
|-------------------|-------|--------------------|
| **Learn Stage Lighting** (learnstagelighting.com) | Tutorials on lighting programming, DMX, fixture types | Understanding fixture behaviour and parameter ranges |
| **Christian Jackson** | EDM production lighting, troubleshooting | Real-world EDM rig walkthrough content |
| **LD-at-Large Podcast** (Chris Lose) | Industry interviews, festival lighting philosophy | Conceptual understanding of design decisions |
| **On Stage Lighting** (onstagelighting.co.uk) | Stage lighting education, tutorials | Technical fundamentals |
| **Tyler Ellis (Singingwithlights)** | Live GrandMA2 programming, touring | Real-time console operation |

### Behind-the-Scenes / Making-Of Content

| Content | Source | Value |
|---------|--------|-------|
| Rammstein Stadium Tour Documentary (Dec 2024) | Official Rammstein YouTube | 1-hour BTS of 1,350-tonne production, pyro regulations per country |
| Deadmau5 Cube V3 BTS | Sam Sheffer (YouTube) | Build process and technical details of Cube |
| Hans Zimmer Live - BTS Lighting | PLSN TV | Orchestral lighting design walkthrough |
| Halsey Tour Production Breakdown | PLSN (Jul 2025) | Full crew interview on production decisions |

### Festival / Tour Full Sets on YouTube

Many festivals officially upload full multi-cam sets. Priority sources:
- **Tomorrowland** official YouTube (Belgian festival, massive production)
- **Ultra Music Festival** official YouTube (Miami, multi-cam with wide shots)
- **Insomniac / EDC** official YouTube (EDC, Dreamstate, Beyond Wonderland)
- **Creamfields** official YouTube (UK festival, multiple stage designs)
- **Boiler Room** (DJ sets in club environments, multiple camera angles)
- **Cercle** (outdoor DJ sets in stunning locations, professional multi-cam)
- **BBC Radio 1 / Essential Mix** recordings with visual component
- **KEXP** (live sessions with professional multi-cam, intimate setting)
- **Printworks London** official channel (industrial venue, high production value)

---

## 11. Industry Publications

| Publication | URL | Focus | Relevance |
|------------|-----|-------|-----------|
| **PLSN** (Projection, Lighting & Staging News) | plsn.com | Tour production breakdowns, designer interviews | Primary source for fixture counts, rig details, designer philosophy |
| **Live Design** | livedesignonline.com | Concert, theatre, theme park production | Technical deep-dives on equipment and design approach |
| **TPi Magazine** | tpimagazine.com | Touring and production industry | European perspective on touring production |
| **FOH Magazine** (Front of House) | fohonline.com | Live sound and production | Production profiles with lighting detail |
| **Lighting & Sound America** | lightingandsoundamerica.com | Entertainment technology | Equipment reviews and installation details |
| **SoundLightUp** | soundlightup.com | Sound and light (French/international) | European production coverage |

---

## 12. Console Programming Resources

### MA Lighting (grandMA3)

- **Official Tutorials**: malighting.com/ma-university/video-tutorials/
- **MA University Training**: Formal courses on grandMA3 software and consoles
- **Free Software**: grandMA3 onPC with MA Start Show (predefined objects and layouts)
- **Key Feature for ML**: New effects concept with multi-step effect sequences nested inside cues/presets
- **Artists Using grandMA3**: Illenium (Chuck Williams), Tool (Mark Jacobson), and industry standard for large-scale touring

### Avolites Titan

- **Official Tutorials**: avolites.com/support/tutorials-guides/
- **Titan Simulator**: Free PC software to simulate any Titan console
- **Manual**: manual.avolites.com (comprehensive, searchable)
- **Key Concepts**: Programmer tracks manual changes, palette-based workflow, cue lists with timeline editing
- **Training Available**: Full-day console training via Avolites

### ChamSys MagicQ

- **Notable User**: Ed Warren (Skrillex/Four Tet MSG show)
- **Philosophy**: Preferred by LDs who prioritise real-time improvisation
- **Key Feature**: Fast busking interface for live-to-music operation

### Console Relevance to ML Training

Understanding console programming paradigms is important for our ALD system because:
1. Professional shows are built from **presets, palettes, and cue stacks** - our model output should map to these abstractions
2. **Timecode vs. manual operation** determines whether lighting is deterministic or improvisational
3. **Effects engines** in consoles (phaser, fan, gradient) create patterns that our model needs to recognise and reproduce
4. **Fixture libraries** define parameter ranges - our DMX output must respect these boundaries

---

## 13. Training Data Diversity Matrix

This matrix ensures our training dataset covers the full range of professional lighting scenarios.

### By Genre

| Genre | Primary Sources | Energy Profile | Typical Palette |
|-------|----------------|----------------|-----------------|
| EDM / House | Prydz, Garrix, Dom Dolla, Fisher, John Summit, Hi Ibiza | High-energy, beat-synced | Saturated, rapidly changing |
| Melodic Bass | Illenium, Rufus Du Sol | Emotional build/release | Warm-to-cool gradients |
| Progressive / Trance | Prydz, Deadmau5, Tiesto | Sustained builds, long transitions | Deep blues, purples, whites |
| Rock / Alt | Muse, Coldplay, Tool | Dynamic range, song-structured | Amber, white, single-colour accents |
| Metal | Metallica, Rammstein | Aggressive, pyro-heavy | Reds, whites, stark contrasts |
| Pop / R&B | Taylor Swift, Beyonce, The Weeknd, Bruno Mars | Narrative, colour-coded eras | Full spectrum, era-specific |
| Hip-Hop | Drake, Kendrick, Travis Scott, Tyler the Creator | Theatrical, dramatic reveals | Minimalist or surreal |
| Dark R&B / Cinematic | The Weeknd | Dystopian, sustained tension | Dark tones, chrome, moonlight |
| Club / Nightclub | Hi Ibiza, Printworks, Fabric, Amnesia | Sustained groove, minimal changes | Dark with accent colours |
| Minimal Techno | Berghain | Near-darkness, precise accents | Almost no colour, stark white |

### By Technique

| Technique | Best Example Sources | Priority |
|-----------|---------------------|----------|
| Beat-synced strobes | Swedish House Mafia, EDM festivals, Fisher | Critical |
| Colour wash transitions | Beyonce, Taylor Swift, Bruno Mars | Critical |
| Beam patterns / aerial | Metallica, Rammstein, Muse, EDC | Critical |
| Build-to-drop energy | All EDM sources, John Summit, Tiesto | Critical |
| Minimalist restraint | Kendrick Lamar, Rufus Du Sol, Fabric, Berghain | High |
| Pyro integration | Rammstein, Travis Scott, Tyler the Creator | High |
| Crowd lighting | Coldplay (PixMob), Drake | High |
| Dystopian / cinematic | The Weeknd, Travis Scott | High |
| Retro-modern (Par Can + movers) | Bruno Mars 24K Magic | High |
| Projection-as-lighting | Tool | Medium |
| Moving set pieces | Deadmau5 Cube, Beyonce | Medium |
| UV / blacklight | Beyonce Renaissance | Medium |
| Improvised/busked | Ed Warren (MSG rave), Tool | High |
| In-the-round / 360 | Metallica M72, Creamfields HALO | Medium |
| Holographic / emerging tech | Amnesia Ibiza (2024), Eric Prydz Holosphere | Medium |
| Near-darkness / negative space | Berghain, Fabric | Medium |
| Scenic-integrated lighting | Tyler the Creator, Travis Scott | Medium |

### By Scale

| Scale | Source | Fixtures | Audience |
|-------|--------|----------|----------|
| Dark Club (minimal) | Berghain, Fabric | 20-100 | 500-1,500 |
| Superclub | Hi Ibiza, Amnesia, Printworks | 100-300 | 2,000-5,000 |
| Theatre/Arena | Kendrick, Drake, Tyler the Creator | 200-600 | 5,000-20,000 |
| Stadium | Metallica, Taylor Swift, The Weeknd, Bruno Mars | 600-1,500 | 40,000-80,000 |
| Festival Mainstage | Tomorrowland, EDC, Creamfields | 1,000-2,000+ | 30,000-100,000 |

---

## Appendix: Video Collection Workflow

### Step 1: Source Identification
Search YouTube for official uploads from artists, festivals, and production companies.
Prioritise multi-cam professional recordings over fan-cam footage.

### Step 2: Quality Assessment
- Check resolution (1080p minimum)
- Verify camera angles include wide shots
- Confirm audio is synced and clear
- Check for excessive post-production colour grading

### Step 3: Metadata Tagging
For each collected video, record:
- Artist, venue, date, duration
- Lighting designer (if known)
- Genre tags (primary + secondary)
- Technique tags (from matrix above)
- Scale (nightclub / arena / stadium / festival)
- Energy profile (low / medium / high / variable)
- Timecoded or improvised

### Step 4: Frame Extraction
- Extract at 5 fps baseline, 30 fps during transitions
- Align audio features (BPM, energy, spectral centroid) to frames
- Generate ALD annotations per the `VIDEO_TO_DMX_TRAINING_PIPELINE.md` spec

### Step 5: Quality Control
- Manual review of 10% sample for annotation accuracy
- Cross-reference with known fixture lists for DMX parameter validation
- Verify genre and technique tags against designer documentation

---

*This catalog should be updated as new tour productions launch and as our model training reveals gaps in coverage.*
