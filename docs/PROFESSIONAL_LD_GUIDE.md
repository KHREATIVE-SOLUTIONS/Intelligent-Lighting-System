# Professional Lighting Design Guide

## Intelligent Lighting System -- AI Decision Engine Reference

This document defines the comprehensive professional requirements, standards, and best practices for automated lighting across four key environments: Theatre, Concert, Festival, and Nightclub. Every recommendation in this guide is intended to be directly implemented in the app's decision engine so that the AI produces output a professional LD with 20 years of touring experience would approve of.

**Target audience:** Developers implementing venue mode logic in the decision engine, effects engine, color mapper, and movement patterns modules.

---

## Table of Contents

1. [Theatre Lighting](#1-theatre-lighting)
2. [Concert Lighting (Indoor Venues)](#2-concert-lighting-indoor-venues)
3. [Festival Lighting](#3-festival-lighting)
4. [Nightclub Lighting](#4-nightclub-lighting)
5. [Universal Professional Standards](#5-universal-professional-standards)
6. [Implementation Recommendations](#6-implementation-recommendations)
7. [Venue Mode Profiles](#7-venue-mode-profiles)

---

## 1. Theatre Lighting

### 1.1 Fundamental Principles

Theatre lighting serves the story. Every cue, every color choice, every fade time exists to serve the narrative, the actor, and the audience's experience of the drama. The five pillars of theatrical lighting design are:

**Visibility.** The audience must be able to see what they need to see. This sounds obvious, but it is the most frequently violated principle. The AI must never sacrifice visibility for atmosphere. If an actor is speaking, their face must be lit. Front light at 45 degrees from the vertical and 45 degrees from center line is the McCandless standard -- the AI should treat this as the default, not the exception.

**Mood.** Color temperature, intensity level, direction of light, and shadow quality all communicate emotional information before a word is spoken. Warm amber light reads as comfort, home, safety. Cold steel blue reads as isolation, night, danger. The AI must understand that in theatre, color communicates subtext, not spectacle.

**Composition.** Stage lighting is a visual art. The eye is drawn to the brightest point on stage. The AI must understand that intensity creates focus -- if the lead actor needs focus, they should be 10-20% brighter than the surrounding wash, not bathed in a followspot while everyone else is in blackout (unless the script calls for that).

**Focus (Selective Visibility).** Not everything on stage should be equally visible at all times. The AI should understand the concept of "area lighting" -- dividing the stage into zones that can be independently controlled. During a monologue downstage center, the upstage areas should be at a lower intensity to draw focus forward.

**Revelation of Form.** Light from a single direction flattens the human body. Theatrical lighting uses multiple angles -- front, side, back, top -- to sculpt the human form in three dimensions. The AI must never rely on front light alone; sidelight gives the body shape, backlight separates the actor from the scenery, and toplight provides definition.

### 1.2 Key Systems

The AI should understand and model these standard theatrical lighting systems:

**Front Wash.** The primary visibility system. Typically warm (L201 Full CT Blue removed, or 3200K-ish source) from one side and cool (L201 or equivalent, 4500K-ish) from the other. This "McCandless method" provides dimensionality even in the front wash. The AI should default to a warm/cool split on front light and never produce flat, single-color front washes.

**Side Light.** Mounted on booms (vertical pipes in the wings) or on ladders. Provides body sculpting and dramatic shadows. Low side light from shin height creates long shadows and drama. Mid-high side light from head height is the workhorse for dance. The AI should use side light intensity as a primary mood lever -- brighter sides mean more drama, more depth.

**Back Light.** Mounted upstage of the performer, pointing toward the audience (but aimed at the performer, not the audience's eyes). Creates separation from scenery, rim lighting on shoulders and hair. A strong backlight on a dimly front-lit actor creates a powerful silhouette. The AI should increase backlight-to-frontlight ratio for dramatic, tense, or mysterious moments.

**Top Light.** Directly overhead. Creates strong downward shadows (under eyes, chin). Used for dance, overhead patterns, and specific dramatic moments. The AI should use top light sparingly for drama -- it is the least flattering angle for actors' faces but creates strong geometric shadows on the floor.

**Specials.** Individual fixtures focused on specific locations for specific moments -- a doorway, a chair, a specific mark on stage. The AI should understand that specials are by nature narrow in both focus and timing. They come in for a specific dramatic beat and go out when that beat is over.

**Cyc Lighting.** The cyclorama (or backdrop) is lit from above and/or below with color washes. The cyc sets the "sky" or overall atmosphere. Dawn is amber-pink from below, midday is pale blue from above, sunset is deep orange-red from below with lavender from above, night is deep blue from above. The AI must change cyc colors slowly -- cyc color changes should be the slowest fades in the show (8-15 second fades are normal; a 3-second cyc change feels jarring).

### 1.3 Color Theory for Theatre

**Color Temperature.** Theatre primarily works in the warm white to daylight range (2700K-6500K). The AI should think in color temperature, not saturated color. A "warm scene" is 2700K-3200K amber. A "cool scene" is 4500K-5600K. Full saturated color is reserved for specific stylistic choices (musicals, expressionist drama, dance).

**Gel Selection Philosophy.** Professional LDs use subtle correction gels far more than saturated color. The AI should model its color choices on these principles:
- Rosco 02 (Bastard Amber) and Rosco 60 (No Color Blue) are the two most-used colors in theatre. They provide warm/cool front washes without calling attention to themselves.
- Lee 201 (Full CT Blue) converts tungsten to approximate daylight. Lee 204 (Full CT Orange) converts daylight to approximate tungsten. These are correction tools, not effects.
- Saturated color on actors' faces makes them look unnatural. The AI should never put saturated red, green, or blue on front wash during dialogue scenes.
- Saturated color on scenery and cyc is acceptable and expected. The cyc can go deep blue while the acting areas stay warm white.

**CTO/CTB Usage.** Color Temperature Orange (CTO) and Color Temperature Blue (CTB) are the theatre LD's primary tools. The AI should model "warm" and "cool" as shifts in color temperature, not as hue changes. A warm scene does not mean "add orange" -- it means "shift the overall color temperature down toward 2700K."

### 1.4 Cue Structure

**How Cues Relate to Script Beats.** Every lighting cue should correspond to a dramatic event: an entrance, an exit, a line of dialogue that shifts the emotional tone, a scene change, a musical button. The AI should never change lighting for no narrative reason. If the audio analysis detects a change in mood or energy, the AI should confirm that a structural shift is occurring before executing a cue.

**Scene Changes.** Scene transitions are one of the few times in theatre where the lighting can be theatrical in its own right -- crossfades between scenes, blackouts for scene shifts, bumps to new scenes. The AI should treat scene transitions as distinct events requiring their own cue logic.

**Emotional Arcs.** Within a scene, the lighting should evolve with the emotional arc. A scene that begins hopeful and ends in despair should slowly shift from warm to cool, from bright to dim, from open (wide focus) to closed (tight focus). These shifts should be imperceptible in the moment -- the audience should feel the change without seeing it happen.

### 1.5 Timing -- Fade Times

Fade timing is where amateur lighting is most easily distinguished from professional work. The AI must have sophisticated fade time logic:

**0-count (snap/bump).** Instantaneous. Used for: lightning, gunshots, sudden reveals, scene-beginning "tops of acts," explosive moments. The AI should reserve 0-count for genuine dramatic shock. Using snap cues casually destroys their impact.

**1-3 count (1-3 seconds).** Quick but visible. Used for: entrances and exits (the light comes up in the time it takes the actor to walk to their mark), quick mood shifts within a scene, lamplight being turned on/off onstage. 3-count is the theatrical workhorse -- fast enough to feel responsive, slow enough not to call attention to itself.

**5-count (5 seconds).** Medium. Used for: establishing a new scene after a transition, time-of-day shifts within a scene, moderate emotional shifts. A 5-count fade feels deliberate and confident.

**8-15 count (8-15 seconds).** Slow. Used for: cyc color changes, sunset/sunrise effects, long emotional builds through a monologue or song, gradual scene shifts. These fades should be imperceptible -- the audience notices the result, not the process.

**20-60 count (20-60 seconds).** Very slow. Used for: the slow onset of night, the gradual dawn, the creeping cold of a tragic final scene. The audience should not be able to perceive the change happening.

**Cross-fades vs. Bump Cues.** A cross-fade dissolves from one state to another. A bump cue snaps to a new state. The AI should default to cross-fades and use bumps only for specific dramatic punctuation. Sequences of rapid bump cues (like concert lighting) are inappropriate for theatre.

### 1.6 Common Mistakes the AI Must Avoid in Theatre

1. **Moving lights moving.** In theatre, if moving lights are used, they are typically preset to a position and used as fixed focus instruments. The AI must disable all movement patterns in theatre mode. If a reposition is needed, it happens during a blackout or a very slow, imperceptible fade.

2. **Strobes.** Strobe effects have no place in straight theatrical lighting (with very rare exceptions for specific effects like a strobe simulating a failing fluorescent tube). The AI must set max_strobe_hz to 0 in theatre mode.

3. **Color chases.** Color chase effects, rainbow effects, and cycling colors are inappropriate for theatre. The AI must disable color chase logic.

4. **Beat-sync anything.** Theatre is not driven by BPM. The AI must disable all beat-sync dimmer effects, beat-locked movement, and audio-reactive intensity changes. Cues in theatre are driven by script events, not audio energy.

5. **Over-saturated color on faces.** The AI must enforce a saturation limit on any light hitting front/side acting areas. Deep saturated color is only appropriate for the cyc, specials, or specific design choices.

6. **Too-fast fades.** A fade time under 2 seconds for a general wash change will look amateurish in 90% of theatrical contexts. The AI's default fade time in theatre mode should be 3-5 seconds.

7. **Uniform intensity.** Every fixture at the same level looks flat and boring. The AI must maintain intensity variation across zones -- brighter where focus is needed, dimmer in surrounding areas.

8. **Ignoring the vertical.** Only front light produces a flat, lifeless look. The AI must always include backlight and/or sidelight components.

### 1.7 How the AI Decision Engine Should Behave for Theatre

The decision engine's current state machine (INTRO, BUILDUP, PEAK, SUSTAIN, BREAKDOWN, OUTRO) is designed for music. For theatre, the state machine should be remapped:

| Music State | Theatre Equivalent | Behavior |
|---|---|---|
| INTRO | Scene Establishment | Slow fade up (5-8 count), establish location/time |
| BUILDUP | Rising Tension | Very slow intensity increase, possible cool shift |
| PEAK | Climactic Moment | Brightest state, possible special, possible snap |
| SUSTAIN | Steady State | Hold current look with minimal variation |
| BREAKDOWN | Resolution/Aftermath | Slow fade toward lower intensity, warmer or cooler |
| OUTRO | Scene End | Slow fade to black (5-10 count) or cross-fade to transition |

All transitions should be slow. The fastest transition in theatre mode should be a 2-second snap for a dramatic peak. The default transition should be 3-5 seconds. Cyc changes should be 8-15 seconds.

---

## 2. Concert Lighting (Indoor Venues)

### 2.1 Rig Design Principles

The AI should understand how professional concert rigs are structured, because this informs how effects should be distributed:

**Truss Positions.**
- **Front Truss:** Wash fixtures for front light, follow spot positions. The AI should map front fixtures to visibility duty -- these provide color wash and face light.
- **Mid Truss:** Primary effects position. Spots, beams, and wash fixtures for the most dramatic looks. The AI should use mid-truss fixtures for the most active effects.
- **Rear Truss:** Backlight and silhouette. Beams pointing into the audience create the most dramatic looks. The AI should use rear fixtures for high-impact moments -- audience blinders, beam fans, backlight walls.
- **Side Positions:** Boom/truss towers stage left and right. Cross-light and sidelight. The AI should use these for accent and texture.

**Fixture Placement Strategy.** A professional rig balances three fixture types:
- **Wash fixtures** (40-50% of rig): Provide base color and visibility. The AI's base layer.
- **Spot fixtures** (25-35% of rig): Provide sharp beams, gobos, and effects. The AI's movement and effect layer.
- **Beam fixtures** (15-25% of rig): Provide pencil beams for dramatic aerials. The AI's impact layer -- used sparingly but powerfully.

### 2.2 Show Flow -- Setlist Lighting

A professional LD thinks about the arc of an entire show, not just individual songs:

**Opener.** High energy, make a statement. This is where the biggest, widest, most impressive looks go. Full rig, saturated color, movement, possibly pyro or confetti. The AI should be at 80-90% of its maximum capability for the opener -- but crucially, not 100%. There must be headroom for the encore.

**Early Set (Songs 2-4).** Settle into the show. Mix of energy levels. The AI should read the setlist energy and provide variety -- do not repeat the opener's intensity for every song.

**Mid Set.** This is where the show breathes. Ballads, acoustic segments, slower songs should get their own distinct looks -- stripped back, intimate, warm. The AI should recognize low-energy songs and respond with restraint, not by trying to compensate.

**Late Set / Main Set Closer.** Building toward the climax. The AI should progressively increase its maximum intensity and effect complexity through the late set, peaking at the main set closer.

**Encore.** The emotional peak of the show. The AI should hold its absolute biggest, most dramatic looks for the encore. If the system has been at full capacity all night, the encore has nowhere to go -- and that is a fundamental failure of show design.

### 2.3 Song-Level Design

This is where the AI's decision engine maps most directly to the current state machine:

**Verse.** Lower intensity (50-70% of the song's peak). Tighter focus -- not every fixture needs to be on. Cooler or more subdued colors. Minimal movement or slow, continuous movement (a gentle circle or sweep). The verse is about intimacy and drawing the audience in. The AI should pull back in verses, not push forward.

Key parameters:
- Intensity: 50-70% of song peak
- Color: Desaturated or cool-shifted, 1-2 colors max
- Movement: Slow continuous (circle_slow, gentle_tilt) or static look
- Dimmer: Gentle breathing or static
- Strobe: OFF

**Pre-Chorus / Build.** Transitional energy. The AI should begin opening up -- more fixtures, slightly brighter, possibly a color shift toward the chorus palette. Movement can accelerate slightly. This is the ramp that makes the chorus feel earned.

Key parameters:
- Intensity: 60-80%, rising
- Color: Transitioning toward chorus palette
- Movement: Increasing speed, possibly adding phase spread
- Dimmer: RAMP_UP or accelerating pulse
- Strobe: OFF (save it)

**Chorus.** Open up. Wider wash, brighter, more saturated color, more fixtures active. Movement should be bigger and more visible. The chorus is the emotional payoff -- the AI should make it feel distinctly different from the verse. The most common amateur mistake is having the chorus look the same as the verse.

Key parameters:
- Intensity: 80-100% of song peak
- Color: Saturated, warm or bright, 2-3 colors
- Movement: Medium-fast, wider amplitude (fast_sweep, circle_fast, ballyhoo)
- Dimmer: Beat sync (four_on_floor or backbeat)
- Strobe: Only on the biggest chorus of the song, if at all

**Bridge.** Something different. The bridge is musically distinct, and the lighting should be too. The AI should introduce a color or look that has not appeared in the song yet. A bridge is a moment of contrast -- if the song has been warm, go cool. If it has been moving, go static.

Key parameters:
- Intensity: Variable -- can be lower or higher than chorus
- Color: New color not used in verse/chorus, or a dramatic single-color wash
- Movement: Different from both verse and chorus
- Dimmer: Different pattern from chorus
- Strobe: Unlikely but possible for effect

**Drop/Peak.** Maximum impact. This is the moment the audience has been waiting for. Every fixture at full. Saturated color. Fast movement or a dramatic static look. Strobe burst on the downbeat. Audience blinders. This is where the AI should deploy its biggest looks -- and crucially, this moment only works if the preceding sections were restrained enough to create contrast.

Key parameters:
- Intensity: 100%
- Color: Maximum saturation, high-contrast
- Movement: Fast chase, ballyhoo, or snap to dramatic static look
- Dimmer: Beat sync with full intensity pattern, or full-on
- Strobe: BURST on the initial hit (2-second burst at 12-15Hz), then transition to beat-locked

**Breakdown.** Strip back. One color. Minimal fixtures. No movement or very slow movement. The breakdown creates tension by removing stimulation. The audience feels the absence of the full rig, and this makes the next chorus or drop more powerful by contrast. The AI must resist the urge to fill the breakdown -- emptiness is the point.

Key parameters:
- Intensity: 20-40%
- Color: Single color wash, often cool (blue, purple, cyan)
- Movement: NONE or very slow (circle_slow)
- Dimmer: Breathing or static
- Strobe: OFF

**Build-Up.** Progressive increase in every parameter. The AI should ramp intensity, movement speed, movement amplitude, color saturation, and potentially strobe frequency over the duration of the build. This is the tension before the release.

Key parameters:
- Intensity: Rising from 30% to 90%
- Color: Shifting toward the drop's palette
- Movement: Accelerating, narrowing (center_out_wave, or sweep increasing speed)
- Dimmer: RAMP_UP or buildup_8 pattern
- Strobe: Slow continuous building to faster (1Hz to 4Hz maximum before drop)

**Outro/Song End.** The AI should bring the song to a definitive close. For songs that end with a big finish, hold the peak look and snap to blackout. For songs that fade, execute a slow fade to lower levels. The gap between songs is critical -- the AI should use this moment to reset, breathe, and prepare a different look for the next song.

### 2.4 Busking Techniques

"Busking" is when an LD improvises lighting to live music in real time, without pre-programmed cues. This is exactly what the AI decision engine does. Here is how a skilled human busker operates:

**What They Watch For:**
- Kick drum hits (low frequency transients) -- these drive dimmer flashes and movement triggers
- Snare hits (mid-high transients) -- these can trigger color bumps or strobe flashes
- Hi-hat patterns -- these indicate tempo and subdivisions
- Vocal presence -- when vocals are present, front light must be adequate; when absent, more freedom for dramatic looks
- Song structure (verse/chorus) -- the busker is always listening 4-8 bars ahead, anticipating the next section
- The artist's energy -- if the performer is at the front of the stage engaging the crowd, the LD opens up; if they step back for a solo, the LD can get more dramatic

**How They Time Hits:**
- The initial color change or movement change happens ON the downbeat of the new section (beat 1 of the chorus, not beat 4 of the verse)
- Dimmer flashes are ON the beat, not behind it
- Movement pattern changes happen at the start of musical phrases (every 4 or 8 bars)
- The busker "loads" the next look in advance and triggers it on the beat

**How the AI Should Implement Busking:**
- The decision engine's state transitions should align to bar boundaries. Do not change states mid-bar unless a genuine transient event (drop, breakdown silence) demands it.
- Pattern changes should happen on beat 1 of a phrase (every 4, 8, or 16 bars depending on intensity of change).
- Small changes (dimmer pattern swap, slight color shift) can happen every 4 bars.
- Medium changes (movement pattern change, color palette shift) should happen every 8 bars.
- Large changes (full look change, static-to-movement switch) should happen every 16 bars or at section boundaries.

### 2.5 Genre-Specific Approaches

#### Rock / Metal

**Look and Feel:** Raw, aggressive, powerful. Dominated by warm/hot colors (reds, ambers, golds) with cool accents (deep blue, white). Backlight-heavy for silhouettes. Audience blinders on the biggest moments.

**Color Palette:**
- Primary: Red (HSV 0, 100%, 90%), Amber (HSV 30, 100%, 100%), Gold (HSV 45, 90%, 95%)
- Secondary: Deep Blue (HSV 230, 90%, 60%), White (0, 0%, 100%)
- Accent: Orange (HSV 20, 100%, 100%), occasionally Purple for breakdowns

**Movement:** Slower and more deliberate than EDM. Ballyhoo and sweeps are common, but quick chases and jerky movement feel wrong. Movement should feel heavy and powerful, not frantic. Mirror sweeps and synchronized movement suit rock better than randomized chases.

**Timing:** On the beat but with a "heavy" feel. Rock sits slightly behind the beat compared to EDM. The AI should use longer attack times on dimmer effects (attack_time: 0.03-0.05 instead of 0.01) and longer decay times for a more weighted feel.

**Strobe:** Sparingly. A single white strobe burst on the biggest moment of the set. Rock shows that strobe every chorus lose their impact. Save it for the guitar solo climax or the final chorus.

**Key Rules for AI:**
- Backlight intensity should be 80-120% of front light (yes, brighter than front)
- Favor single-color washes (all red, all amber) over multicolor
- Movement speed range: 0.1-0.6 Hz (slower than EDM)
- Default fade time: 0.5-2.0 seconds (faster than theatre, slower than EDM)
- Strobe budget: maximum 2-3 bursts per song, 0 for ballads

#### EDM / Electronic

**Look and Feel:** Saturated, futuristic, high-energy. Heavily synchronized to the beat grid. Color is a primary tool. Movement is constant and complex. Strobes are expected and embraced.

**Color Palette:**
- Primary: Cyan (HSV 180, 100%, 100%), Magenta (HSV 300, 100%, 100%), UV/Deep Blue (HSV 260, 100%, 80%)
- Secondary: White (for strobe moments), Green (HSV 120, 100%, 100%)
- Accent: Yellow (HSV 60, 100%, 100%), Pink (HSV 330, 80%, 100%)

**Movement:** Fast, complex, heavily phased. Phase spread should be maximum (1.0) for most effects. Chase patterns, circle chases, and counter-rotation are staples. Movement should be tightly locked to BPM using beat_divisor sync.

**Timing:** Extremely tight to the grid. Every flash, every movement hit, every color change should land precisely on the beat. EDM audiences are acutely aware of timing -- even 50ms of latency between the kick drum and the light flash feels "off." The AI should use the shortest possible attack times (attack_time: 0.01 or less).

**Strobe:** Expected and frequent. Strobe bursts on drops are mandatory. Beat-locked strobe during sustained high-energy sections is standard. The AI should use the full range of strobe capabilities, respecting safety limits.

**Key Rules for AI:**
- Beat sync must be precise (the system's beat detection latency is the bottleneck)
- Movement speed range: 0.2-2.0 Hz, BPM-locked
- Color changes should be sudden (bump cues on phrase boundaries)
- Strobe on every major drop, beat-locked strobe during sustained peaks
- Full fixture count during drops, minimal during breakdowns
- UV effect: simulate UV by using deep blue-purple (HSV 270-280, 90%, 30-50%) at low intensity

#### Pop

**Look and Feel:** Bright, colorful, audience-friendly. Pop lighting should feel professional and polished, never aggressive or alienating. Variety of looks is important -- pop shows change looks more frequently than rock shows.

**Color Palette:**
- Primary: Bright Pink (HSV 330, 70%, 100%), Lavender (HSV 270, 40%, 90%), Coral (HSV 15, 60%, 100%)
- Secondary: Teal (HSV 175, 70%, 80%), Bright Blue (HSV 210, 80%, 100%), Gold (HSV 45, 80%, 100%)
- Accent: White, Pale Yellow

**Movement:** Moderate speed, smooth. Pop movement should feel polished, not chaotic. Synchronized circles, smooth sweeps, and gentle chases. Avoid anything that looks aggressive (fast alternating, random walk).

**Timing:** On the beat but "friendly." Not as aggressively locked as EDM. The AI can afford slightly softer attack times (0.02-0.04s) and can use cross-fades between looks rather than snap changes.

**Key Rules for AI:**
- Maintain at least 60% front light at all times (the artist must always be visible)
- Change looks more frequently than rock (every 4-8 bars instead of 8-16)
- Use 3-4 distinct color palettes per song (verse palette, chorus palette, bridge palette)
- Follow spots: if the system supports them, they should track the performer; the AI should boost front intensity during vocal sections
- Strobe budget: 1-2 per song maximum, and only short bursts (1 second)

#### Hip-Hop / R&B

**Look and Feel:** Moody, atmospheric, stylish. Single-color washes dominate. The vibe is cool and confident, not frantic. Negative space (areas of darkness) is a tool.

**Color Palette:**
- Primary: Deep Purple (HSV 280, 80%, 60%), Gold (HSV 45, 100%, 90%), Royal Blue (HSV 230, 80%, 70%)
- Secondary: Deep Red (HSV 350, 90%, 50%), White (for accents), Magenta (HSV 310, 70%, 80%)
- Accent: Amber (HSV 35, 100%, 100%), Cyan (HSV 180, 60%, 70%)

**Movement:** Minimal. The vibe is about presence, not movement. When movement is used, it should be slow and deliberate -- a very slow ballyhoo or a gentle sweep. Fast movement contradicts the genre's aesthetic.

**Timing:** Behind the beat. Hip-hop lighting should feel laid-back. The AI should use slightly longer attack times (0.03-0.06s) and longer fade times (1-3 seconds for color changes). Beat-sync dimmer effects should use half-time or syncopated patterns rather than four-on-the-floor.

**Key Rules for AI:**
- Single-color washes are the default (not multi-color)
- Backlight and sidelight dominate; front light is minimal (40-60% typical)
- Intensity range is narrow (30-80% typical; rarely at 100%)
- Movement speed range: 0.05-0.3 Hz (very slow)
- Strobe: rarely, and only white blinder-style, not patterned
- Haze is essential -- beams without haze look wrong for this genre

#### Jazz / Blues

**Look and Feel:** Warm, intimate, respectful. The lighting should be almost invisible -- supporting the music without drawing attention to itself. Think of a smoky jazz club: amber light, deep shadows, pools of light on performers.

**Color Palette:**
- Primary: Amber (HSV 35, 80%, 80%), Warm White (HSV 35, 20%, 90%), Steel Blue (HSV 215, 40%, 50%)
- Secondary: Pale Lavender (HSV 270, 20%, 80%), Straw (HSV 50, 40%, 90%)
- Accent: Deep Blue (HSV 230, 70%, 40%) for moody moments

**Movement:** None. Jazz lighting does not move. If moving lights are in the rig, they should be static-focused and used as conventional fixtures. The AI must disable all movement patterns for jazz.

**Timing:** Very slow. Fade times of 5-15 seconds. Changes happen between songs or during long musical phrases, not on individual beats. The AI should not react to individual beats in jazz -- it should respond to overall energy trends over 30-60 second windows.

**Key Rules for AI:**
- Movement: NONE
- Strobe: NEVER
- Dimmer effects: Breathing at very slow speed (0.1-0.2 Hz) maximum
- Color changes: Cross-fade over 5-15 seconds minimum
- Intensity range: 30-70% (never full blast)
- Beat detection should be disabled or heavily smoothed -- jazz has irregular meter and the AI should not try to follow it mechanically

#### Country

**Look and Feel:** Warm, naturalistic, approachable. Country lighting should feel like warm sunlight or campfire light. Clean, simple, effective. The audience should feel welcome, not overwhelmed.

**Color Palette:**
- Primary: Warm White (HSV 35, 15%, 95%), Amber (HSV 35, 70%, 90%), Straw (HSV 50, 50%, 90%)
- Secondary: Pale Blue (HSV 210, 30%, 80%), Soft Lavender (HSV 270, 25%, 80%)
- Accent: Deep Amber (HSV 25, 90%, 80%) for emotional moments

**Movement:** Very minimal. A gentle ballyhoo at most. Country lighting feels best when it is still and confident. The AI should default to static looks with very slow, subtle movement.

**Timing:** Natural and musical, not mechanical. Country has a strong sense of phrasing (verse-chorus-verse) and the AI should change looks at phrase boundaries. Beat-sync effects should be soft (sine pulse, not square pulse) if used at all.

**Key Rules for AI:**
- Maximum saturation: 70% (no eye-searing saturated colors)
- Movement speed range: 0.05-0.2 Hz maximum
- Default fade time: 2-5 seconds
- Strobe: never for standard country; very rare short bursts for modern country-pop crossover
- Front light should always be adequate -- the artist is the focus, not the light show
- Backlight in amber/warm white for a natural "golden hour" feel

### 2.6 Timing and Feel

**On the Beat vs. Behind vs. Ahead.**

The "tightness" of lighting to the beat varies by genre:

| Genre | Beat Relationship | AI Attack Time | Notes |
|---|---|---|---|
| EDM/Techno | Exactly on beat | 0.005-0.01s | Machine-precise |
| Pop | On beat | 0.02-0.03s | Tight but human |
| Rock | Slightly heavy | 0.03-0.05s | Weight, not latency |
| Hip-Hop | Behind the beat | 0.04-0.06s | Deliberate swagger |
| Jazz | Ignore beats | N/A | Follow phrases, not beats |
| Country | On the phrase | 0.03-0.05s | Musical, not mechanical |

The AI should adjust its beat-trigger response time based on the active genre profile.

### 2.7 Common Rookie Mistakes the AI Must Never Make

1. **Everything at 100% all the time.** This is the single most common amateur mistake. If the rig is at full power during the verse, the chorus has nowhere to go. The AI must maintain dynamic range -- verses should be at 50-70% so choruses can reach 80-100%.

2. **Random color vomit.** Rapidly cycling through random colors with no musical relationship is the hallmark of a bad light show. The AI should select 2-3 colors per song section and commit to them.

3. **Movement for movement's sake.** Not every fixture needs to be moving all the time. Static moments have power. The AI should use MovementType.NONE for 30-50% of verse sections.

4. **Strobe abuse.** Using strobes in every chorus means they have no impact. The AI should budget strobes: maximum 3-4 strobe moments per song, with at least 30 seconds between bursts.

5. **No blackout discipline.** A blackout at the end of a song is a powerful moment of punctuation. The AI should execute clean blackouts on the last beat of songs that end with a definitive stop.

6. **Identical looks across songs.** If every song looks the same, the audience checks out. The AI must vary its primary color palette, movement pattern, and overall intensity level between songs.

7. **Competing with the performer.** If the artist is doing something onstage that deserves focus (solo, crowd interaction, emotional moment), the lighting should pull back and let them shine. High-energy lighting during a quiet crowd moment is jarring.

8. **Slow transitions when speed is needed.** The moment a chorus hits, the new look must be there. A 2-second fade into a chorus feels late. The AI should use bump cues (0-count) for chorus entries and drop hits.

9. **Forgetting backlight.** A show lit only from the front looks like a school play. The AI must always include backlight, especially during high-energy moments.

10. **Same movement pattern for too long.** The same circle pattern running for 3 minutes becomes wallpaper. The AI should change movement patterns every 8-16 bars.

---

## 3. Festival Lighting

### 3.1 Scale Differences

Festival lighting operates under fundamentally different constraints than club or concert lighting:

**Distance.** The audience is 10-200 meters from the stage, compared to 5-30 meters in a club. This means:
- Small, detailed movements are invisible. The AI must increase movement amplitude by 30-50% compared to concert mode.
- Subtle color shifts are lost. The AI must use more saturated colors with higher contrast.
- Fine-grained dimmer effects (gentle breathing, gaussian noise) are imperceptible. The AI should use bolder, more graphic dimmer effects.

**Scale of Rig.** Festival rigs are physically larger -- more fixtures, more truss, longer throws. The AI should take advantage of this by using wider phase spreads and more complex multi-group choreography.

**Competition.** The lighting rig is competing with the sun, with IMAG screens, with neighboring stages, and with the audience's attention span. The AI must be more assertive and bolder in festival mode.

### 3.2 Daylight Considerations

This is the single biggest technical challenge unique to festival lighting:

**Afternoon Slots (Full Daylight).** Lighting is essentially invisible. The AI should:
- Use only the brightest fixtures (no subtle washes)
- Focus on audience blinders and stage presence rather than aerials
- Minimize movement (the audience cannot see beams in daylight)
- Use strobe effects only as blinder-style impact moments
- Set minimum intensity to 80% (nothing below 80% will be visible)

**Sunset Slots (Golden Hour / Dusk).** The transition from day to night is magical and the AI should exploit it:
- Begin with daytime constraints
- Progressively lower the minimum intensity as ambient light drops
- Introduce warm colors that complement the sunset
- Start using beam effects as soon as haze becomes visible in the beams (typically 30-45 minutes before full dark)
- This transition should happen automatically over 60-90 minutes

**Night Slots (Full Dark).** Full capability is available:
- The AI can use the full dynamic range (0-100% intensity)
- Beam effects and aerials are at their most effective
- This is when the biggest, most dramatic looks should be deployed

### 3.3 Audience Scale

Movements need to be bigger and slower for festival audiences. The human eye at 100+ meters cannot track fast, small movement. Key adjustments:

- **Movement speed:** Reduce maximum by 30% compared to concert (a sweep that takes 1 second in a club should take 1.5 seconds at a festival)
- **Movement amplitude:** Increase by 30-50% (pan_amplitude: 90-120 degrees instead of 60-80)
- **Color saturation:** Increase to 80-100% (no subtle pastels)
- **Phase spread:** Keep at maximum (1.0) -- the phase difference between fixtures is what creates visible effects at distance
- **Dimmer effects:** Use square and triangle waves rather than sine for crisper, more visible patterns

### 3.4 Multi-Artist Rigs

Festival rigs must serve multiple artists across different genres. The AI should:

- Have a neutral "reset" state between acts (all fixtures parked center, warm white wash)
- Be able to switch venue profiles rapidly between genre modes
- Maintain a base look that works for any genre (warm front wash, cool backlight)
- Adapt to the artist's genre within the first 30-60 seconds of their set using audio analysis

### 3.5 Headliner vs. Support

The AI should scale its ambition based on the artist's slot position:

| Slot | Intensity Range | Strobe Budget | Movement Complexity | Color Variety |
|---|---|---|---|---|
| Opening act (daylight) | 80-100% (flat, daytime) | 0-1 per song | Minimal | 1-2 colors |
| Mid-afternoon | 70-100% | 1-2 per song | Simple | 2-3 colors |
| Late afternoon | 50-100% | 2-3 per song | Moderate | 3-4 colors |
| Early evening | 30-100% | 3-4 per song | Full | Full palette |
| Sub-headliner | 20-100% | 4-5 per song | Full | Full palette |
| Headliner | 0-100% (full range) | Unlimited within safety | Maximum | Full palette + specials |

### 3.6 Weather and Environmental Factors

**Haze Management.** Haze is essential for beam visibility, but wind disperses it rapidly on outdoor stages. The AI should:
- In high-wind conditions, increase intensity and saturation to compensate for reduced beam visibility
- Use wider beam angles when haze is sparse
- Favor wash effects over beam effects in windy conditions

**Rain.** Rain creates natural haze and makes beams incredibly visible. The AI can actually reduce intensity slightly in rain while maintaining dramatic beam looks.

**Extreme Heat.** Some fixtures may overheat in direct sunlight and high ambient temperatures. The AI should be aware of fixture duty cycling limits and avoid sustained full-intensity operation during hot afternoon slots.

### 3.7 IMAG Interaction

IMAG (Image Magnification) video screens are ubiquitous at festivals. The AI must be aware of how lighting interacts with cameras:

- **Avoid extreme backlight-only looks during camera-heavy moments.** The cameras need some front fill to expose the artist's face. A silhouette looks great from the audience but produces an unusable camera shot.
- **Strobe and cameras.** Fast strobes can produce rolling shutter artifacts on camera. The AI should consider reducing strobe frequency slightly during heavily filmed moments (8-10Hz max instead of 12-15Hz).
- **Color rendering on camera.** Deep saturated reds can clip to orange on camera. The AI should be aware that what looks right in person may not look right on screen. Adding a small amount of blue to reds (shifting from HSV 0 to HSV 350) helps camera reproduction.

---

## 4. Nightclub Lighting

### 4.1 DJ Set Lighting

Club lighting is fundamentally different from concert lighting because:

**Continuous flow.** DJ sets do not have discrete songs with clear beginnings and endings. Tracks are mixed together, and the energy flow is continuous. The AI should not treat each track as a separate entity. Instead, it should track the overall energy trajectory.

**Energy management over hours.** A DJ set can last 2-8 hours. The AI must think in macro-arcs:
- **Opening hour:** Low intensity, warm colors, slow movement. Establish atmosphere. Intensity at 30-50%.
- **Second hour:** Begin building. More color variety, moderate movement. Intensity 40-60%.
- **Peak hours (hours 3-5 for a long set):** Full capability. Maximum intensity, full color palette, active movement, strobes on big moments.
- **Closing hour:** Gradual wind-down. Return to simpler looks, reduce intensity, warm up colors. End the night with a feeling of completion, not an abrupt stop.

**The AI should track set position** (how long has the DJ been playing) and adjust its maximum and minimum intensity ranges accordingly.

### 4.2 Dance Floor Priority

Club lighting must light FOR dancers, not AT dancers. The key distinction:

**Lighting AT dancers** means pointing fixtures directly at the dance floor at high intensity. This is uncomfortable, overheats the crowd, and creates glare. The AI should:
- Avoid sustained high-intensity front-facing wash directly on the dance floor
- Use overhead beam effects that create patterns on the floor rather than blinding the dancers
- Keep the most intense effects (blinders, strobes) brief

**Lighting FOR dancers** means creating an environment that makes dancing feel natural and exciting:
- Moving beams above the crowd create a sense of spectacle without direct glare
- Color washes on walls and ceiling create atmosphere
- Rhythmic dimmer effects create a pulse that dancers can feel
- The dance floor should be lit primarily by overhead and peripheral light, not direct frontal

**Intensity on the dance floor:** The AI should target 40-70% average intensity on the dance floor, with peaks to 100% on big moments. Sustained 100% is physically uncomfortable in a hot, crowded club.

### 4.3 Genre-Specific Club Lighting

#### House / Techno

**Look and Feel:** Hypnotic, repetitive, minimalist. House and techno lighting should create a trance-like state. Patterns repeat for long periods. Color changes are slow and evolutionary. The vibe is "the lights are breathing with the music."

**Color Palette:**
- House: Warm tones -- amber, orange, warm white, with occasional cool blue or green accent
- Techno: Cold tones -- white, ice blue, green, with occasional deep red or purple accent

**Movement:** Slow, continuous, repetitive. A single movement pattern (slow circle or sweep) can run for 10-20 minutes. Changes are gradual. The AI should resist the urge to change patterns frequently -- in house/techno, consistency IS the effect.

**Dimmer:** Sine pulse locked to BPM is the primary tool. The pulse should be gentle (min 0.4, max 1.0) for house, sharper (min 0.1, max 1.0) for techno.

**Strobe:** House: rare, short, gentle. Techno: more frequent but still disciplined. Never sustained -- always brief punctuation on the biggest moments.

**Key Rules for AI:**
- Pattern change interval: 16-32 bars (not every 4-8 bars like concerts)
- Color change interval: 32-64 bars (slow evolution)
- Movement speed: 0.1-0.3 Hz (very slow)
- Strobe budget per hour: 4-6 moments for house, 8-12 for techno
- Intensity rarely exceeds 80% for house; techno can hit 100% but should spend most time at 50-70%

#### Drum and Bass

**Look and Feel:** Fast, aggressive, relentless. DnB runs at 170-180 BPM, and the lighting must keep up. Sharp, staccato effects. High contrast between on and off states.

**Color Palette:**
- Primary: Green (HSV 120, 100%, 90%), Purple (HSV 280, 90%, 70%), White
- Secondary: Red (HSV 0, 100%, 80%), Cyan (HSV 180, 80%, 90%)
- Accent: Yellow, Orange

**Movement:** Fast chases and alternating patterns. Beat-locked movement at full or half-beat speed. Phase spread at maximum for aggressive chase effects.

**Strobe:** Heavy. DnB audiences expect strobe. Beat-locked strobe on drops, burst strobe on the biggest moments. The AI should use the full strobe range within safety limits.

**Key Rules for AI:**
- Beat divisor: 1.0 or 2.0 (movement on every beat or half-beat)
- Movement speed: 0.5-2.0 Hz (fast)
- Dimmer effects: Square pulse and kick follower for sharp, staccato feel
- Attack time: 0.005-0.01s (razor sharp)
- Strobe budget per hour: 15-20 moments (more than any other genre)

#### Trance

**Look and Feel:** Ethereal, sweeping, emotional. Trance lighting should feel like a journey -- slowly building, reaching peaks, then descending into valleys. Long, slow builds with dramatic payoffs.

**Color Palette:**
- Primary: Deep Blue (HSV 230, 80%, 60%), Purple (HSV 270, 70%, 70%), Cyan (HSV 190, 70%, 80%)
- Secondary: White, Pale Pink (HSV 330, 40%, 90%)
- Accent: Gold (HSV 45, 80%, 90%) for emotional peaks, Green (HSV 140, 60%, 70%) for breakdowns

**Movement:** Slow, sweeping, expansive. Wide-amplitude horizontal sweeps and gentle circles. Movement should feel like waves -- not mechanical, but organic and flowing.

**Build-ups:** Trance is defined by its builds. The AI should have a sophisticated build-up algorithm for trance:
- Begin with minimal movement, low intensity, single cool color
- Over 16-64 bars, progressively add: more fixtures, brighter intensity, faster movement, shift toward warmer color
- At the peak, full rig, full color, full movement, possible strobe burst
- After the peak, immediately strip back and begin building again

**Key Rules for AI:**
- Build-up detection is critical -- the AI must identify trance builds early and ramp accordingly
- Pattern change interval: 16-64 bars (very slow)
- Movement speed: 0.1-0.5 Hz (slow to moderate)
- Fade times: 2-8 seconds for color transitions
- Strobe: only on the biggest breakdowns (1-2 per 30-minute segment)

#### Bass Music / Dubstep

**Look and Feel:** Aggressive, dark, punchy. Dominated by the drop/breakdown cycle. Heavy use of strobes and sharp, staccato effects on the drops. Atmospheric and minimal during breakdowns.

**Color Palette:**
- Primary: Purple (HSV 275, 90%, 60%), Green (HSV 120, 100%, 80%), White (for strobes)
- Secondary: Deep Red (HSV 350, 100%, 50%), Cyan (HSV 180, 80%, 70%)
- Accent: Orange (HSV 20, 100%, 90%) for high energy

**Movement:** Dual personality. During breakdowns: minimal, slow, atmospheric. During drops: aggressive, fast, sharp. The AI should have two distinct movement profiles and switch between them on structural transitions.

**Drops:** This genre lives and dies by its drops. The AI should deploy maximum impact:
- Snap to a dramatic static look or fast chase on beat 1 of the drop
- White strobe burst (2 seconds, 12-15Hz)
- Full intensity, maximum saturation
- Sharp, staccato dimmer patterns

**Breakdowns:** Near-darkness. Single color at low intensity. Perhaps a single slow-moving fixture. The contrast between breakdown and drop is what makes bass music lighting work.

**Key Rules for AI:**
- The dynamic range between breakdown and drop should be maximum (10% to 100%)
- Movement speed during drops: 0.5-2.0 Hz
- Movement speed during breakdowns: 0.05-0.2 Hz
- Strobe on every significant drop
- Beat detection must handle the half-time feel common in dubstep (the "drop" often feels like half the BPM)

### 4.4 VIP / Bottle Service Areas

Non-dance-floor zones require different treatment:

- **Intensity:** 20-40% of dance floor levels. VIP areas should be ambient, not blinding.
- **Color:** Warm, flattering tones. Amber, soft gold, pale lavender. Nothing that makes skin look unhealthy (avoid pure green, cyan, or deep blue on faces).
- **Movement:** NONE. Static ambient wash only.
- **Strobe:** NEVER in VIP areas. Guests are eating, drinking, and socializing.
- **Synchronization:** VIP lighting should be loosely related to the main dance floor (same color family, much lower intensity) but never directly synchronized to the beat.

The AI should support zone-based output where VIP fixtures follow different rules than dance floor fixtures.

### 4.5 Resident DJ vs. Guest

**Resident DJ.** The venue's regular DJ. The AI should maintain the venue's signature look -- the house colors, the typical intensity range, the "brand" of the lighting. Consistency across resident nights builds venue identity.

**Guest DJ.** The AI should adapt to the guest's genre and energy while still maintaining core venue identity. This means:
- Keep 1-2 venue signature colors in the palette
- Adjust intensity, movement, and strobe parameters to match the guest's genre
- Potentially shift the color temperature range to match the guest's vibe

### 4.6 Marathon Sets

Managing visual interest over 4-8 hour sets requires macro-level thinking:

**Palette Rotation.** The AI should not cycle through all 8 palettes randomly. Instead, it should have a structured rotation:
- Use 2-3 colors for 20-30 minutes
- Transition to a new palette over 2-4 minutes
- Avoid returning to a recently used palette for at least 60 minutes
- Track which palettes have been used and ensure variety

**Movement Pattern Rotation.** Similarly, the AI should rotate through movement patterns on a 15-30 minute cycle. No single pattern should dominate for more than 5 minutes unless the genre demands it (house/techno excepted).

**Intensity Arc.** Over a full night:

```
  100%|                    ****
      |               ****    ****
   80%|          ****             ****
      |     ****                       ****
   60%|****                                 ****
      |                                          ****
   40%|                                               ****
      |
   20%|
      +-------------------------------------------->
       Open  Hour1  Hour2  Hour3  Hour4  Hour5  Close
```

The AI should enforce this macro-arc even when the decision engine wants to push higher during the opening hours.

### 4.7 UV and Blacklight

UV/blacklight is a signature element of club lighting:

**When to Use:**
- During sustained dance sections (not during transitions)
- Paired with minimal visible light for maximum UV effect
- During breakdowns before drops (UV in near-darkness creates anticipation)
- During special moments (midnight, headline DJ intro)

**How to Use Effectively:**
- UV looks best with minimal competing visible light. The AI should reduce wash intensity to 20-30% when UV is the primary effect.
- UV should run for a minimum of 30 seconds to have visual impact (white clothing needs time to become visible).
- UV combined with strobe creates a dramatic flickering blacklight effect.
- The AI can simulate UV by using deep blue-purple (HSV 270-280) at low intensity with other sources dimmed.

**When NOT to Use:**
- During high-energy full-rig moments (UV gets washed out by intense visible light)
- For more than 5 continuous minutes (it loses its novelty)
- In combination with warm white light (the color temperatures clash)

---

## 5. Universal Professional Standards

### 5.1 The "Less Is More" Principle

The most important principle in professional lighting design: restraint creates impact. The AI must internalize this at every level:

- **Not every fixture needs to be on.** Using 4 of 12 fixtures creates a more focused, intentional look than using all 12 at 50%.
- **Not every moment needs an effect.** Static holds with good color and composition are often more powerful than movement.
- **Not every beat needs a flash.** Dimmer effects and beat sync should be reserved for sections where rhythmic lighting serves the music.
- **Not every drop needs a strobe.** Even in EDM, some drops are more powerful when answered with a full color wash and no strobe.

The AI should maintain a "restraint counter" -- if it has been deploying maximum effects for more than 16 bars, it should consciously pull back to create headroom for the next peak.

### 5.2 The "Save It" Principle

Professional LDs always hold something in reserve. The AI should structure its effect deployment like this:

| Song Position | Available Resources Used |
|---|---|
| Verse 1 | 30-40% |
| Chorus 1 | 60-70% |
| Verse 2 | 40-50% (slightly more than Verse 1) |
| Chorus 2 | 70-80% |
| Bridge | 50-60% (different, not bigger) |
| Final Chorus | 90-100% |
| Outro | 20-30% |

And at the show level:

| Show Position | Maximum Available |
|---|---|
| Songs 1-3 | 80% |
| Songs 4-6 | 85% |
| Songs 7-9 | 90% |
| Main set closer | 95% |
| Encore | 100% |

The AI should never deploy 100% of its capabilities before the absolute peak of the performance.

### 5.3 Contrast and Dynamics

**If everything is at 100%, nothing feels special.** This is the fundamental law of dynamic range in lighting.

The AI must maintain contrast ratios:
- **Within a song:** The dimmest moment should be no more than 40-60% of the brightest moment.
- **Within a set:** The lowest song should be no more than 50% of the highest song.
- **Within a section:** Verse should be 60-75% of chorus intensity.

**Temporal contrast:** A blackout followed by a full-intensity snap is the highest contrast available. The AI should not use this more than 2-3 times per set.

**Color contrast:** Complementary colors (blue/orange, red/green, purple/yellow) create the strongest visual contrast. The AI should use complementary color transitions at section boundaries.

### 5.4 Color Mixing Rules

**Colors That Complement:**
- Blue and Amber/Orange (theatrical classic)
- Magenta and Green (EDM classic)
- Purple and Gold (hip-hop classic)
- Red and Cyan (high contrast)
- Deep Blue and Warm White (concert classic)

**Colors That Clash:**
- Red and Magenta (too close, muddies to pink)
- Green and Yellow (sickly, unflattering)
- Orange and Red (indistinguishable at distance)
- Cyan and Green (blend into an unappealing teal)

**Color Temperature Consistency.** Within a single "look," all lights should be within the same color temperature family. The AI should never mix warm amber front light with cool blue front light unless deliberately creating a warm/cool split (McCandless method for theatre).

**The Rule of Three.** A lighting look should use no more than 3 colors at once. Two is often better. One can be the most powerful. The AI should limit its color count:
- Breakdowns: 1 color
- Verses: 1-2 colors
- Choruses: 2-3 colors
- Drops/peaks: 2-3 colors at maximum saturation

### 5.5 Movement Discipline

**Not every fixture needs to move all the time.** The AI should categorize fixtures into roles:

- **Static base:** 30-50% of fixtures hold static positions providing base wash and structure
- **Slow movement:** 20-30% of fixtures on slow, continuous movement (circles, sweeps)
- **Active effects:** 20-30% of fixtures on faster, more dramatic movement
- **Accent/special:** 10-20% held in reserve for specific moments

This distribution should shift based on song section:
- Verse: 60% static, 30% slow, 10% active
- Chorus: 30% static, 30% slow, 40% active
- Drop: 10% static, 20% slow, 70% active
- Breakdown: 70% static, 30% slow, 0% active

### 5.6 Blackout Rules

**When blackouts are effective:**
- At the end of a song that ends with a hard stop (snare hit, final chord, cut-off)
- As punctuation between songs (1-3 seconds of darkness creates anticipation)
- During a dramatic pause in the music (a "dead stop" before a drop)
- At the end of a show

**When blackouts are jarring:**
- During a crossfade between songs (the transition should be smooth, not interrupted)
- In the middle of a continuous DJ mix (kills the flow)
- As a crutch for not having the next look ready
- Multiple times within a single song (once is dramatic, three times is annoying)

**Blackout implementation:** A proper blackout must be instantaneous (0-count). A blackout that takes 0.5 seconds is not a blackout -- it is a fast fade and reads as a mistake. The AI must snap to zero on blackout triggers.

**Coming out of blackout:** The first look after a blackout should be strong and intentional. Do not fade up timidly from black -- either snap to the new look or fade up confidently over 2-3 seconds.

### 5.7 Safety Standards

**Strobe Limits.** The current system's limits are sound and should be enforced rigidly:
- 4 Hz maximum for continuous strobe (sustained over 3 seconds)
- 15 Hz maximum for bursts (under 4 seconds)
- Minimum 2-second cooldown after burst before next burst
- No strobe during clearly theatrical/seated performances
- The AI should track cumulative strobe exposure and reduce strobe frequency as total exposure increases (no more than 30 seconds of total strobe in any 5-minute window)

**Emergency Lighting.** The AI must never interfere with emergency lighting systems. In the event of a blackout command, the system should release all DMX output to allow emergency lighting to take over.

**Photosensitive Epilepsy.** The AI should implement an additional "safe mode" that reduces all strobe to 3 Hz maximum and eliminates rapid intensity changes (over 50% change in under 100ms). This mode should be easily activatable by the operator.

**Thermal Safety.** The AI should implement duty cycling awareness for fixtures that are operated at maximum intensity. No fixture should be held at 100% intensity for more than 30 continuous minutes without a reduction period.

### 5.8 Haze/Fog Usage

**Haze is essential.** Without atmospheric haze, beam effects are invisible. The AI should be aware that:
- Beam effects (aerial beams, laser-like pencil beams) require haze to be visible
- If the system detects that beam effects are in use, it should flag that haze is recommended
- Haze works best at a consistent, light level -- heavy bursts of fog look different from consistent haze
- Indoor venues retain haze well; outdoor venues and spaces with strong HVAC can require heavy hazing

**Too much haze:**
- Reduces contrast (everything looks flat)
- Can trigger fire alarms
- Creates visibility issues for the audience
- Makes the venue feel stuffy and uncomfortable

**Too little haze:**
- Beam effects are invisible
- Aerial looks disappear
- The rig looks like static points of light rather than a dynamic environment

The AI should note in its documentation that its beam and aerial effects assume adequate haze is present.

### 5.9 Fixture Maintenance Awareness

While the AI does not directly maintain fixtures, it should be aware of:

- **Lamp hours.** Fixtures have limited lamp life. The AI should not hold fixtures at 100% unnecessarily. If a fixture is not contributing to the current look, dim it or turn it off. This extends lamp life and reduces power consumption.
- **Color mixing accuracy.** LED fixtures shift color as they age and heat up. The AI should not rely on precise color matching between fixtures -- it should design looks that work even if individual fixture color calibration varies slightly.
- **Movement calibration.** Moving lights drift in calibration over time. The AI should use looks that do not depend on precise aim (wide washes rather than tight spot positions) unless the system has been recently calibrated.

---

## 6. Implementation Recommendations

### 6.1 Decision Engine Modifications Per Venue Mode

#### Theatre Mode

The decision engine state machine should be fundamentally restructured for theatre:

**Disable audio-reactive behavior.** In theatre mode, the decision engine should NOT respond to real-time audio analysis. Instead, it should operate on preset cue lists or very slowly evolving states.

**State transition rules:**
- Minimum state duration: 30 seconds (no rapid state changes)
- All transitions use cross-fades (minimum 2-second fade)
- PEAK state should never enable strobes or fast movement
- Energy detection thresholds should be doubled (energy must be much higher before triggering a transition)
- The decision engine should weight "stay in current state" at 80%+ probability

**New constraints to enforce:**
- `max_fixture_speed`: 0 (no movement)
- `max_color_saturation`: 0.6 (for acting areas), 1.0 (for cyc/scenery)
- `min_fade_time`: 2.0 seconds
- `beat_sync_enabled`: False
- `strobe_enabled`: False
- `color_chase_enabled`: False

#### Concert Mode

The decision engine is closest to its current implementation for concerts. Key modifications:

**Genre-aware state transitions:**
- For Rock: increase state duration minimums by 50% (hold looks longer)
- For EDM: decrease state duration minimums by 30% (change more frequently)
- For Pop: use standard durations
- For Hip-Hop: increase by 100% (hold looks much longer)
- For Jazz: increase by 300% (minimal changes)

**Beat-sync precision per genre:**
- EDM: Zero tolerance -- trigger exactly on beat detection
- Rock: Allow 20-50ms of built-in delay for "weight"
- Hip-Hop: Allow 40-80ms of built-in delay for "swagger"
- Jazz: Disable beat sync entirely

**Strobe allocation per genre:**

```python
strobe_budget = {
    "edm": {"per_song": 6, "per_set": -1},      # Unlimited per set
    "rock": {"per_song": 2, "per_set": 20},
    "pop": {"per_song": 1, "per_set": 10},
    "hip_hop": {"per_song": 1, "per_set": 8},
    "jazz": {"per_song": 0, "per_set": 0},
    "country": {"per_song": 0, "per_set": 2},
}
```

#### Festival Mode

Festival mode extends concert mode with additional constraints:

**Daylight awareness.** Add a `daylight_level` parameter (0.0 = full dark, 1.0 = full daylight) that modifies:
- `min_intensity`: 0.3 + daylight_level * 0.5 (brighter minimum in daylight)
- `movement_effectiveness`: 1.0 - daylight_level * 0.7 (reduce movement in daylight)
- `strobe_effectiveness`: max(0, 1.0 - daylight_level * 0.8) (strobe useless in daylight)
- `beam_effectiveness`: max(0, 1.0 - daylight_level * 0.9) (beams useless in daylight)

**Scale adjustments:**
- `movement_amplitude_multiplier`: 1.4 (40% wider)
- `movement_speed_multiplier`: 0.7 (30% slower)
- `color_saturation_minimum`: 0.7 (more saturated)
- `fade_time_multiplier`: 0.8 (slightly faster transitions -- need to be more decisive at festivals)

#### Nightclub Mode

The decision engine needs significant restructuring for clubs:

**Continuous flow mode.** The silence-based song change detection should be disabled for club mode. Instead, the AI should detect track transitions through:
- Gradual BPM changes (DJ mixing)
- Energy trend changes over 30-60 second windows
- Spectral character shifts

**Macro-arc enforcement.** Add a `set_position` tracker (0.0 = start of night, 1.0 = end of night) that caps maximum intensity:

```python
max_intensity_cap = {
    "0.00-0.15": 0.5,    # Opening: max 50%
    "0.15-0.30": 0.65,   # Warming up: max 65%
    "0.30-0.50": 0.8,    # Building: max 80%
    "0.50-0.75": 1.0,    # Peak hours: full
    "0.75-0.90": 0.9,    # Late peak: slight pullback
    "0.90-1.00": 0.6,    # Closing: wind down
}
```

**Pattern change intervals.** The pattern change cooldown should be significantly longer for clubs:
- `cooldown_bars["pattern_change"]`: 32 (instead of 8)
- `cooldown_bars["static_look"]`: 64 (instead of 16)
- `cooldown_bars["strobe_burst"]`: 128 (instead of 64)

### 6.2 New Color Palettes for the Color Mapper

The following palettes should be added to `color_mapper.py` to support the genre-specific approaches outlined above:

```python
# New palettes to add to ColorPalette enum:
JAZZ = "jazz"                       # Warm amber, steel blue
COUNTRY = "country"                 # Warm white, amber, pale blue
TRANCE = "trance"                   # Deep blue, purple, cyan
DNB = "dnb"                         # Green, purple, white
BASS_MUSIC = "bass"                 # Purple, green, white
THEATRE_WARM = "theatre_warm"       # CTO range
THEATRE_COOL = "theatre_cool"       # CTB range
FESTIVAL_DAY = "festival_day"       # High-saturation, high-value visible in daylight
UV_BLACKLIGHT = "uv"                # Deep blue-purple simulating UV

# New hue ranges for _palette_hues:
# ColorPalette.JAZZ: [(30, 45), (210, 225)]           # Amber, Steel Blue
# ColorPalette.COUNTRY: [(30, 55), (200, 220)]         # Amber-Straw, Pale Blue
# ColorPalette.TRANCE: [(220, 280), (180, 200)]        # Blue-Purple, Cyan
# ColorPalette.DNB: [(110, 140), (270, 290)]            # Green, Purple
# ColorPalette.BASS_MUSIC: [(270, 290), (110, 130)]     # Purple, Green
# ColorPalette.THEATRE_WARM: [(25, 45)]                  # Amber range only
# ColorPalette.THEATRE_COOL: [(200, 230)]                # Steel-Blue range only
# ColorPalette.FESTIVAL_DAY: [(0, 360)]                  # Full spectrum, forced high sat
# ColorPalette.UV_BLACKLIGHT: [(265, 285)]               # Narrow UV-purple range
```

### 6.3 Movement Pattern Preferences Per Venue Type

```python
VENUE_MOVEMENT_PREFERENCES = {
    "theatre": {
        "allowed": ["none"],       # No movement in theatre
        "default": "none",
        "speed_range": [0, 0],
        "amplitude_range": [0, 0],
    },

    "concert": {
        "rock": {
            "preferred": [
                "ballyhoo", "mirror", "h_sweep", "circle", "synchronized",
            ],
            "avoid": ["random_walk", "pan_chase"],
            "speed_range": [0.1, 0.6],
            "amplitude_range": [40, 80],
        },
        "edm": {
            "preferred": [
                "circle_chase", "pan_chase", "counter_rotation",
                "alternating", "center_out",
            ],
            "avoid": ["random_walk"],
            "speed_range": [0.2, 2.0],
            "amplitude_range": [45, 90],
        },
        "pop": {
            "preferred": [
                "circle", "h_sweep", "mirror", "ballyhoo",
            ],
            "avoid": ["random_walk", "counter_rotation"],
            "speed_range": [0.15, 0.8],
            "amplitude_range": [40, 75],
        },
        "hip_hop": {
            "preferred": ["none", "h_sweep", "ballyhoo"],
            "avoid": [
                "random_walk", "pan_chase", "alternating", "circle_chase",
            ],
            "speed_range": [0.05, 0.3],
            "amplitude_range": [30, 60],
        },
        "jazz": {
            "preferred": ["none"],
            "avoid": "all_movement",
            "speed_range": [0, 0],
            "amplitude_range": [0, 0],
        },
        "country": {
            "preferred": ["none", "ballyhoo", "h_sweep"],
            "avoid": [
                "random_walk", "pan_chase", "alternating", "counter_rotation",
            ],
            "speed_range": [0.05, 0.2],
            "amplitude_range": [30, 50],
        },
    },

    "festival": {
        # Same genre preferences as concert but with scale adjustments
        "amplitude_multiplier": 1.4,
        "speed_multiplier": 0.7,
    },

    "nightclub": {
        "house": {
            "preferred": ["circle", "h_sweep", "spiral"],
            "avoid": ["random_walk", "alternating"],
            "speed_range": [0.1, 0.3],
            "amplitude_range": [35, 65],
        },
        "techno": {
            "preferred": ["circle", "pan_chase", "mirror", "center_out"],
            "avoid": ["random_walk"],
            "speed_range": [0.1, 0.5],
            "amplitude_range": [40, 75],
        },
        "dnb": {
            "preferred": [
                "pan_chase", "alternating", "circle_chase", "counter_rotation",
            ],
            "avoid": [],
            "speed_range": [0.3, 2.0],
            "amplitude_range": [45, 85],
        },
        "trance": {
            "preferred": ["h_sweep", "circle", "spiral", "ballyhoo"],
            "avoid": ["random_walk", "alternating"],
            "speed_range": [0.1, 0.5],
            "amplitude_range": [50, 90],
        },
        "bass_music": {
            "preferred": [
                "pan_chase", "alternating", "counter_rotation", "mirror",
            ],
            "avoid": [],
            "speed_range": [0.05, 1.5],
            "amplitude_range": [40, 85],
        },
    },
}
```

### 6.4 Decision Engine State Transition Rules Per Venue Type

```python
# Minimum bars in state before transition is allowed
STATE_DURATION_MINIMUMS = {
    "theatre": {
        "INTRO": 32,
        "BUILDUP": 16,
        "PEAK": 16,
        "SUSTAIN": 32,
        "BREAKDOWN": 16,
        "OUTRO": 16,
    },
    "concert": {
        "INTRO": 4,
        "BUILDUP": 4,
        "PEAK": 4,
        "SUSTAIN": 8,
        "BREAKDOWN": 4,
        "OUTRO": 4,
    },
    "festival": {
        "INTRO": 4,
        "BUILDUP": 4,
        "PEAK": 4,
        "SUSTAIN": 8,
        "BREAKDOWN": 4,
        "OUTRO": 4,
    },
    "nightclub": {
        "INTRO": 8,
        "BUILDUP": 8,
        "PEAK": 8,
        "SUSTAIN": 16,
        "BREAKDOWN": 8,
        "OUTRO": 8,
    },
}

# Energy thresholds for state transitions (higher = harder to trigger)
ENERGY_THRESHOLDS = {
    "theatre": {
        "buildup_trend": 0.25,       # Very high threshold (rarely triggers)
        "drop_bass": 0.95,            # Almost never triggers
        "breakdown_energy": 0.15,     # Only in near-silence
        "breakdown_trend": -0.2,
    },
    "concert": {
        "buildup_trend": 0.1,
        "drop_bass": 0.8,
        "breakdown_energy": 0.3,
        "breakdown_trend": -0.1,
    },
    "festival": {
        "buildup_trend": 0.1,
        "drop_bass": 0.8,
        "breakdown_energy": 0.3,
        "breakdown_trend": -0.1,
    },
    "nightclub": {
        "buildup_trend": 0.12,
        "drop_bass": 0.82,
        "breakdown_energy": 0.25,
        "breakdown_trend": -0.12,
    },
}
```

### 6.5 New Rules and Constraints for the AI

The following rules should be implemented as hard constraints in the effects engine:

```python
VENUE_CONSTRAINTS = {
    "theatre": {
        "movement_allowed": False,
        "strobe_allowed": False,
        "beat_sync_allowed": False,
        "color_chase_allowed": False,
        "max_color_saturation": 0.6,       # For acting areas
        "max_cyc_saturation": 1.0,         # Full saturation on cyc OK
        "min_fade_time_seconds": 2.0,
        "max_snap_cues_per_scene": 2,       # Budget for bump cues
        "intensity_range": [0.0, 0.85],     # Never fully blasting in theatre
        "color_temp_range_kelvin": [2700, 6500],
    },

    "concert": {
        "movement_allowed": True,
        "strobe_allowed": True,
        "beat_sync_allowed": True,
        "color_chase_allowed": True,
        "max_color_saturation": 1.0,
        "min_fade_time_seconds": 0.0,       # Snap cues allowed
        "intensity_range": [0.0, 1.0],
        "min_backlight_ratio": 0.3,         # Backlight at least 30% of front
        "max_same_pattern_bars": 32,         # Force pattern change after 32 bars
        "max_same_palette_songs": 3,         # Force palette change after 3 songs
    },

    "festival": {
        "movement_allowed": True,
        "strobe_allowed": True,
        "beat_sync_allowed": True,
        "color_chase_allowed": True,
        "max_color_saturation": 1.0,
        "min_color_saturation": 0.7,        # Must be saturated (visibility)
        "min_fade_time_seconds": 0.0,
        "intensity_range": [0.3, 1.0],      # Never too dim at festivals
        "movement_amplitude_multiplier": 1.4,
        "movement_speed_multiplier": 0.7,
    },

    "nightclub": {
        "movement_allowed": True,
        "strobe_allowed": True,
        "beat_sync_allowed": True,
        "color_chase_allowed": True,
        "max_color_saturation": 1.0,
        "min_fade_time_seconds": 0.0,
        "intensity_range": [0.0, 1.0],
        "min_pattern_change_bars": 16,       # Hold patterns longer in clubs
        "max_dance_floor_sustained_intensity": 0.7,
        "vip_max_intensity": 0.4,
        "vip_strobe_allowed": False,
        "vip_movement_allowed": False,
    },
}
```

### 6.6 Suggested Additions to the Effects Engine

**1. Venue Mode Manager.** A new class that wraps the existing effects engine and enforces venue-specific constraints:

```python
class VenueMode(Enum):
    THEATRE = "theatre"
    CONCERT = "concert"
    FESTIVAL = "festival"
    NIGHTCLUB = "nightclub"

class VenueModeManager:
    """Enforces venue-specific constraints on the effects engine."""

    def __init__(self, effects_engine):
        self.engine = effects_engine
        self.mode = VenueMode.CONCERT  # Default
        self.genre = "edm"             # Default
        self.daylight_level = 0.0       # Festival only
        self.set_position = 0.0         # Nightclub only (0-1 over full night)

    def set_mode(self, mode, genre=None):
        """Set venue mode and apply all constraints."""
        self.mode = mode
        if genre:
            self.genre = genre
        self._apply_constraints()

    def _apply_constraints(self):
        """Apply all venue constraints to the effects engine."""
        constraints = VENUE_CONSTRAINTS[self.mode.value]
        # Apply strobe limits
        if not constraints["strobe_allowed"]:
            self.engine.config.strobe_enabled = False
        # Apply movement limits
        if not constraints.get("movement_allowed", True):
            self.engine.config.movement_enabled = False
        # ... apply all other constraints
```

**2. Macro-Arc Tracker.** For nightclub mode, a class that tracks the progression of a multi-hour set and adjusts parameters accordingly:

```python
class MacroArcTracker:
    """Tracks set progression and enforces intensity arcs over hours."""

    def __init__(self, expected_duration_hours=4.0):
        self.start_time = None
        self.expected_duration = expected_duration_hours * 3600
        self.palette_history = []
        self.palette_change_times = []

    def get_intensity_cap(self):
        """Get current maximum intensity based on set position."""
        position = self.get_set_position()
        # Piecewise linear intensity cap
        if position < 0.15:
            return 0.5
        elif position < 0.3:
            return 0.5 + (position - 0.15) / 0.15 * 0.15  # 0.5 to 0.65
        elif position < 0.5:
            return 0.65 + (position - 0.3) / 0.2 * 0.15    # 0.65 to 0.8
        elif position < 0.75:
            return 1.0                                        # Full
        elif position < 0.9:
            return 1.0 - (position - 0.75) / 0.15 * 0.1     # 1.0 to 0.9
        else:
            return 0.9 - (position - 0.9) / 0.1 * 0.3       # 0.9 to 0.6
```

**3. Strobe Budget System.** A system that tracks strobe usage and enforces per-song and per-set limits:

```python
class StrobeBudget:
    """Tracks and limits strobe usage per song and per set."""

    def __init__(self, genre="edm"):
        self.genre = genre
        self.song_strobe_count = 0
        self.set_strobe_count = 0
        self.last_strobe_time = 0
        self.budgets = {
            "edm": {"per_song": 6, "per_set": -1},
            "rock": {"per_song": 2, "per_set": 20},
            "pop": {"per_song": 1, "per_set": 10},
            "hip_hop": {"per_song": 1, "per_set": 8},
            "jazz": {"per_song": 0, "per_set": 0},
            "country": {"per_song": 0, "per_set": 2},
        }

    def can_strobe(self):
        """Check if strobe is allowed within budget."""
        budget = self.budgets.get(self.genre, {"per_song": 4, "per_set": -1})
        if budget["per_song"] >= 0 and self.song_strobe_count >= budget["per_song"]:
            return False
        if budget["per_set"] >= 0 and self.set_strobe_count >= budget["per_set"]:
            return False
        # Minimum 30 seconds between strobes
        import time
        if time.time() - self.last_strobe_time < 30:
            return False
        return True

    def record_strobe(self):
        """Record a strobe usage."""
        import time
        self.song_strobe_count += 1
        self.set_strobe_count += 1
        self.last_strobe_time = time.time()

    def new_song(self):
        """Reset per-song counter."""
        self.song_strobe_count = 0
```

**4. Dynamic Range Enforcer.** A system that ensures the AI maintains proper contrast:

```python
class DynamicRangeEnforcer:
    """Ensures the AI maintains contrast and dynamic range."""

    def __init__(self):
        self.intensity_history = []  # Rolling window of 60 seconds
        self.peak_intensity_last_60s = 0.0
        self.min_intensity_last_60s = 1.0

    def get_adjusted_intensity(self, requested, state):
        """Adjust intensity to maintain dynamic range."""
        # If we have been at high intensity for too long, reduce
        if self.peak_intensity_last_60s > 0.9:
            time_at_high = self._time_above(0.85)
            if time_at_high > 30:  # 30 seconds at over 85%
                # Force a pullback
                max_allowed = 0.7
                return min(requested, max_allowed)

        # If everything has been at similar levels, create contrast
        range_last_60 = self.peak_intensity_last_60s - self.min_intensity_last_60s
        if range_last_60 < 0.3:  # Less than 30% range
            # The next transition should be more dramatic
            if state == "BREAKDOWN":
                return min(requested, 0.3)  # Force breakdown to be dimmer
            elif state == "PEAK":
                return max(requested, 0.9)  # Force peak to be brighter

        return requested
```

---

## 7. Venue Mode Profiles

These are concrete parameter profiles ready for implementation. Each value has been calibrated based on professional standards.

### THEATRE_MODE

```python
THEATRE_MODE = {
    # === SAFETY AND CONSTRAINTS ===
    "max_strobe_hz": 0,                    # No strobes in theatre
    "strobe_enabled": False,
    "beat_sync_enabled": False,            # Not driven by audio beats
    "color_chase_enabled": False,
    "movement_enabled": False,             # No movement -- fixtures preset and held

    # === MOVEMENT (if movement were allowed, e.g., for dance theatre) ===
    "movement_speed_range": [0.02, 0.1],   # Extremely slow, imperceptible
    "movement_amplitude_pan": [5, 20],     # Tiny, subtle
    "movement_amplitude_tilt": [3, 15],
    "movement_smoothing": 0.05,            # Very smooth interpolation
    "allowed_movement_types": ["none"],

    # === COLOR ===
    "color_temp_range_kelvin": [2700, 6500],
    "max_color_saturation_acting_area": 0.5,   # Subtle color on faces
    "max_color_saturation_cyc": 1.0,           # Full saturation on cyc OK
    "max_color_saturation_backlight": 0.8,
    "default_color_temp": 3200,                 # Warm tungsten default
    "color_transition_time_seconds": 8.0,       # Slow color changes
    "palette": "theatre_warm",

    # === INTENSITY ===
    "intensity_range": [0.0, 0.85],            # Never full blast
    "default_intensity": 0.65,
    "min_front_light_during_dialogue": 0.5,    # Visibility guarantee
    "backlight_to_front_ratio": [0.3, 1.2],    # Can be brighter than front for drama

    # === TIMING ===
    "fade_time_default_seconds": 4.0,
    "fade_time_minimum_seconds": 2.0,
    "fade_time_cyc_seconds": 10.0,
    "snap_cue_budget_per_scene": 2,
    "crossfade_default": True,                  # Always cross-fade unless snap

    # === DECISION ENGINE ===
    "state_minimum_duration_bars": 32,
    "state_transition_probability_stay": 0.85,  # 85% chance to stay in state
    "energy_sensitivity": 0.2,                  # Very low audio reactivity
    "audio_analysis_enabled": False,            # Cue-based, not audio-based

    # === DIMMER EFFECTS ===
    "allowed_dimmer_types": [
        "none",            # Static intensity
        "sine_pulse",      # Very slow breathing only
        "ramp_up",         # For builds
        "ramp_down",       # For fades
    ],
    "dimmer_speed_range": [0.05, 0.2],         # Very slow
    "dimmer_min_intensity": 0.2,

    # === BLACKOUT ===
    "blackout_fade_time": 0.0,                 # Blackouts are instant
    "restore_fade_time": 3.0,                  # But coming out of black is a fade
}
```

### CONCERT_MODE

```python
CONCERT_MODE = {
    # === SAFETY AND CONSTRAINTS ===
    "max_strobe_hz": 4,                    # 4Hz continuous max
    "max_strobe_burst_hz": 15,             # 15Hz burst max
    "max_strobe_burst_duration": 3.0,      # 3 second bursts
    "strobe_enabled": True,
    "beat_sync_enabled": True,
    "color_chase_enabled": True,
    "movement_enabled": True,

    # === MOVEMENT ===
    "movement_speed_range": [0.1, 1.5],
    "movement_amplitude_pan": [30, 90],
    "movement_amplitude_tilt": [20, 60],
    "movement_smoothing": 0.25,
    "phase_spread_range": [0.3, 1.0],
    "allowed_movement_types": [
        "none", "h_sweep", "v_sweep", "figure_8", "pan_chase",
        "tilt_chase", "alternating", "circle", "spiral", "mirror",
        "center_out", "outside_in", "tilt_bump", "pan_bump",
        "ballyhoo", "circle_chase", "figure_8_mirror", "counter_rotation",
        "synchronized",
    ],
    "max_same_pattern_bars": 32,

    # === COLOR ===
    "color_temp_range_kelvin": [2200, 8000],
    "max_color_saturation": 1.0,
    "color_transition_time_seconds": 0.5,      # Fast color changes OK
    "palette_lock_per_song": True,              # Keep palette within a song
    "max_colors_per_look": 3,

    # === INTENSITY ===
    "intensity_range": [0.0, 1.0],             # Full range
    "verse_intensity_range": [0.4, 0.7],
    "chorus_intensity_range": [0.7, 1.0],
    "breakdown_intensity_range": [0.15, 0.4],
    "drop_intensity": 1.0,
    "min_backlight_ratio": 0.3,

    # === TIMING ===
    "fade_time_default_seconds": 0.5,
    "fade_time_minimum_seconds": 0.0,          # Snap cues allowed
    "snap_on_chorus_entry": True,
    "snap_on_drop": True,
    "crossfade_on_verse": True,

    # === DECISION ENGINE ===
    "state_minimum_duration_bars": 4,
    "state_transition_probability_stay": 0.4,
    "energy_sensitivity": 1.0,
    "pattern_change_cooldown_bars": 8,
    "static_look_cooldown_bars": 16,
    "strobe_cooldown_bars": 32,

    # === DIMMER EFFECTS ===
    "allowed_dimmer_types": [
        "none", "sine_pulse", "triangle", "square",
        "beat_sync", "kick_follower", "ramp_up", "ramp_down",
        "exp_decay", "flicker", "gaussian",
    ],
    "dimmer_speed_range": [0.2, 4.0],
    "dimmer_min_intensity": 0.0,

    # === STROBE BUDGET ===
    "strobe_budget_per_song": 4,
    "strobe_min_interval_seconds": 20,
    "strobe_burst_on_drop": True,
    "strobe_beat_locked_during_peak": True,

    # === DYNAMIC RANGE ===
    "min_verse_chorus_contrast": 0.25,         # Chorus at least 25% brighter
    "max_sustained_peak_bars": 16,              # Force pullback after 16 bars
    "blackout_on_song_end": True,               # Clean blackout on hard endings

    # === GENRE OVERRIDES (applied on top of base concert mode) ===
    "genre_profiles": {
        "rock": {
            "movement_speed_range": [0.1, 0.6],
            "fade_time_default_seconds": 1.0,
            "beat_attack_delay_ms": 35,
            "preferred_palettes": ["rock"],
            "strobe_budget_per_song": 2,
            "backlight_emphasis": 1.3,
        },
        "edm": {
            "movement_speed_range": [0.2, 2.0],
            "fade_time_default_seconds": 0.1,
            "beat_attack_delay_ms": 5,
            "preferred_palettes": ["edm", "techno"],
            "strobe_budget_per_song": 6,
            "beat_sync_precision": "tight",
        },
        "pop": {
            "movement_speed_range": [0.15, 0.8],
            "fade_time_default_seconds": 0.3,
            "beat_attack_delay_ms": 20,
            "preferred_palettes": ["pop"],
            "strobe_budget_per_song": 1,
            "min_front_light": 0.6,
        },
        "hip_hop": {
            "movement_speed_range": [0.05, 0.3],
            "fade_time_default_seconds": 2.0,
            "beat_attack_delay_ms": 55,
            "preferred_palettes": ["hip_hop"],
            "strobe_budget_per_song": 1,
            "max_color_count": 1,
            "intensity_range": [0.2, 0.8],
        },
        "jazz": {
            "movement_speed_range": [0, 0],
            "movement_enabled": False,
            "beat_sync_enabled": False,
            "strobe_enabled": False,
            "fade_time_default_seconds": 8.0,
            "preferred_palettes": ["jazz"],
            "intensity_range": [0.3, 0.7],
            "max_color_saturation": 0.5,
        },
        "country": {
            "movement_speed_range": [0.05, 0.2],
            "fade_time_default_seconds": 3.0,
            "beat_attack_delay_ms": 40,
            "preferred_palettes": ["country"],
            "strobe_budget_per_song": 0,
            "max_color_saturation": 0.7,
            "intensity_range": [0.4, 0.9],
        },
    },
}
```

### FESTIVAL_MODE

```python
FESTIVAL_MODE = {
    # === SAFETY AND CONSTRAINTS ===
    "max_strobe_hz": 4,
    "max_strobe_burst_hz": 12,             # Slightly lower for camera friendliness
    "max_strobe_burst_duration": 2.5,
    "strobe_enabled": True,
    "beat_sync_enabled": True,
    "color_chase_enabled": True,
    "movement_enabled": True,

    # === SCALE ADJUSTMENTS ===
    "movement_amplitude_multiplier": 1.4,   # 40% wider for visibility at distance
    "movement_speed_multiplier": 0.7,       # 30% slower for readability at distance
    "color_saturation_minimum": 0.7,        # Must be punchy at distance
    "color_saturation_multiplier": 1.2,     # Push saturation higher

    # === MOVEMENT ===
    "movement_speed_range": [0.07, 1.0],   # Slower range than concert (scaled)
    "movement_amplitude_pan": [50, 120],    # Wider than concert
    "movement_amplitude_tilt": [30, 80],
    "movement_smoothing": 0.2,
    "phase_spread_range": [0.5, 1.0],      # Higher minimum spread
    "allowed_movement_types": [
        "none", "h_sweep", "v_sweep", "figure_8", "pan_chase",
        "tilt_chase", "alternating", "circle", "spiral", "mirror",
        "center_out", "outside_in", "ballyhoo", "circle_chase",
        "figure_8_mirror", "counter_rotation", "synchronized",
    ],

    # === COLOR ===
    "color_temp_range_kelvin": [2200, 8000],
    "max_color_saturation": 1.0,
    "min_color_saturation": 0.7,           # Always punchy
    "color_transition_time_seconds": 0.3,
    "palette_lock_per_song": True,

    # === INTENSITY ===
    "intensity_range": [0.0, 1.0],
    "daylight_min_intensity": 0.8,          # In daylight, floor is 80%
    "dusk_min_intensity": 0.4,
    "night_min_intensity": 0.0,
    "min_backlight_ratio": 0.4,             # More backlight for distance readability

    # === DAYLIGHT SYSTEM ===
    "daylight_mode_enabled": True,
    "daylight_level": 0.0,                  # 0.0=dark, 1.0=full sun (set by operator)

    # === TIMING ===
    "fade_time_default_seconds": 0.3,
    "fade_time_minimum_seconds": 0.0,

    # === DECISION ENGINE ===
    "state_minimum_duration_bars": 4,
    "energy_sensitivity": 1.0,
    "pattern_change_cooldown_bars": 8,

    # === IMAG CAMERA CONSIDERATIONS ===
    "camera_mode_enabled": False,           # When True, adjusts for cameras
    "camera_max_strobe_hz": 10,             # Reduced for rolling shutter
    "camera_min_front_light": 0.4,          # Ensure face visibility for cameras
    "camera_red_hue_shift": -10,            # Shift reds toward magenta for camera

    # === SLOT PROFILES ===
    "slot_profiles": {
        "opener_daylight": {
            "intensity_range": [0.8, 1.0],
            "strobe_budget_per_song": 0,
            "movement_enabled": False,
            "color_strategy": "bright_contrast",
        },
        "mid_afternoon": {
            "intensity_range": [0.6, 1.0],
            "strobe_budget_per_song": 1,
            "movement_enabled": True,
        },
        "sunset": {
            "intensity_range": [0.3, 1.0],
            "strobe_budget_per_song": 3,
            "color_transition_time": 1.0,
        },
        "headliner_night": {
            "intensity_range": [0.0, 1.0],
            "strobe_budget_per_song": -1,    # Unlimited
            "movement_enabled": True,
            "all_effects_available": True,
        },
    },
}
```

### NIGHTCLUB_MODE

```python
NIGHTCLUB_MODE = {
    # === SAFETY AND CONSTRAINTS ===
    "max_strobe_hz": 4,
    "max_strobe_burst_hz": 15,
    "max_strobe_burst_duration": 3.0,
    "strobe_enabled": True,
    "beat_sync_enabled": True,
    "color_chase_enabled": True,
    "movement_enabled": True,

    # === CONTINUOUS FLOW ===
    "song_detection_mode": "continuous",    # Not silence-gap based
    "track_transition_detection": True,     # Detect DJ mixing transitions
    "energy_smoothing_window_seconds": 30,  # Smooth over 30 seconds
    "palette_change_interval_minutes": 20,  # Minimum between palette changes
    "palette_cooldown_minutes": 60,         # Before reusing a palette

    # === MOVEMENT ===
    "movement_speed_range": [0.08, 1.5],
    "movement_amplitude_pan": [30, 80],
    "movement_amplitude_tilt": [20, 55],
    "movement_smoothing": 0.2,
    "pattern_change_cooldown_bars": 32,     # Hold patterns much longer
    "allowed_movement_types": [
        "none", "h_sweep", "v_sweep", "figure_8", "pan_chase",
        "tilt_chase", "alternating", "circle", "spiral", "mirror",
        "center_out", "outside_in", "ballyhoo", "circle_chase",
        "figure_8_mirror", "counter_rotation", "synchronized",
    ],

    # === COLOR ===
    "color_temp_range_kelvin": [2000, 10000],  # Full range including UV simulation
    "max_color_saturation": 1.0,
    "color_transition_time_seconds": 2.0,      # Medium transitions
    "color_change_interval_bars": 32,           # Change slowly

    # === INTENSITY ===
    "intensity_range": [0.0, 1.0],
    "max_sustained_dance_floor_intensity": 0.7, # Comfort limit
    "vip_intensity_range": [0.1, 0.4],
    "bar_area_intensity_range": [0.2, 0.5],

    # === MACRO ARC ===
    "macro_arc_enabled": True,
    "set_duration_hours": 4.0,
    "intensity_arc": {
        "0.00": 0.50,
        "0.15": 0.65,
        "0.30": 0.80,
        "0.50": 1.00,
        "0.75": 1.00,
        "0.85": 0.90,
        "0.95": 0.60,
        "1.00": 0.40,
    },

    # === TIMING ===
    "fade_time_default_seconds": 0.5,
    "fade_time_minimum_seconds": 0.0,

    # === DECISION ENGINE ===
    "state_minimum_duration_bars": 8,
    "state_transition_probability_stay": 0.6,
    "energy_sensitivity": 0.8,

    # === STROBE BUDGET (per hour, not per song) ===
    "strobe_budget_per_hour": 10,
    "strobe_min_interval_seconds": 45,

    # === ZONES ===
    "zone_profiles": {
        "dance_floor": {
            "intensity_range": [0.0, 1.0],
            "all_effects": True,
            "strobe_allowed": True,
            "beat_sync": True,
        },
        "vip": {
            "intensity_range": [0.1, 0.4],
            "all_effects": False,
            "strobe_allowed": False,
            "beat_sync": False,
            "movement_allowed": False,
            "color_saturation_max": 0.4,
            "preferred_color_temp": 2700,
        },
        "bar": {
            "intensity_range": [0.2, 0.5],
            "all_effects": False,
            "strobe_allowed": False,
            "beat_sync": False,
            "movement_allowed": False,
        },
        "entrance": {
            "intensity_range": [0.3, 0.6],
            "color_sync_with_dance_floor": True,
            "intensity_sync_factor": 0.5,
            "strobe_allowed": False,
        },
    },

    # === UV SYSTEM ===
    "uv_enabled": True,
    "uv_min_duration_seconds": 30,
    "uv_max_duration_seconds": 300,
    "uv_visible_light_max_during": 0.3,
    "uv_cooldown_minutes": 15,

    # === GENRE OVERRIDES ===
    "genre_profiles": {
        "house": {
            "movement_speed_range": [0.1, 0.3],
            "pattern_change_cooldown_bars": 64,
            "color_change_interval_bars": 64,
            "dimmer_effect": "sine_pulse",
            "dimmer_speed_range": [0.3, 0.8],
            "dimmer_min_intensity": 0.4,
            "strobe_budget_per_hour": 5,
            "max_intensity": 0.8,
            "preferred_palettes": ["house"],
        },
        "techno": {
            "movement_speed_range": [0.1, 0.5],
            "pattern_change_cooldown_bars": 32,
            "color_change_interval_bars": 32,
            "dimmer_effect": "sine_pulse",
            "dimmer_speed_range": [0.5, 1.5],
            "dimmer_min_intensity": 0.1,
            "strobe_budget_per_hour": 10,
            "max_intensity": 0.9,
            "preferred_palettes": ["techno"],
        },
        "dnb": {
            "movement_speed_range": [0.3, 2.0],
            "pattern_change_cooldown_bars": 16,
            "color_change_interval_bars": 16,
            "dimmer_effect": "kick_follower",
            "dimmer_speed_range": [1.0, 4.0],
            "dimmer_min_intensity": 0.0,
            "strobe_budget_per_hour": 20,
            "max_intensity": 1.0,
            "beat_attack_delay_ms": 5,
            "preferred_palettes": ["dnb"],
        },
        "trance": {
            "movement_speed_range": [0.1, 0.5],
            "pattern_change_cooldown_bars": 32,
            "color_change_interval_bars": 32,
            "dimmer_effect": "sine_pulse",
            "dimmer_speed_range": [0.2, 0.6],
            "dimmer_min_intensity": 0.2,
            "strobe_budget_per_hour": 6,
            "max_intensity": 0.9,
            "buildup_detection_sensitivity": 1.5,
            "preferred_palettes": ["trance"],
        },
        "bass_music": {
            "movement_speed_range": [0.05, 1.5],
            "pattern_change_cooldown_bars": 16,
            "color_change_interval_bars": 16,
            "dimmer_effect": "beat_sync",
            "dimmer_speed_range": [0.5, 2.0],
            "dimmer_min_intensity": 0.0,
            "strobe_budget_per_hour": 15,
            "max_intensity": 1.0,
            "breakdown_intensity_max": 0.2,
            "drop_intensity_min": 0.9,
            "preferred_palettes": ["bass", "dubstep"],
        },
    },
}
```

---

## Appendix A: Quick Reference -- What Changes Per Venue

| Parameter | Theatre | Concert | Festival | Nightclub |
|---|---|---|---|---|
| Strobe Max Hz | 0 | 4 cont / 15 burst | 4 cont / 12 burst | 4 cont / 15 burst |
| Movement | OFF | Full range | Wide + slow | Genre-dependent |
| Move Speed (Hz) | 0 | 0.1-1.5 | 0.07-1.0 | 0.08-1.5 |
| Move Amplitude | 0 | 30-90 deg | 50-120 deg | 30-80 deg |
| Color Saturation | 0-0.6 | 0-1.0 | 0.7-1.0 | 0-1.0 |
| Default Fade (s) | 4.0 | 0.5 | 0.3 | 0.5 |
| Min Fade (s) | 2.0 | 0.0 | 0.0 | 0.0 |
| Beat Sync | OFF | ON | ON | ON |
| Intensity Range | 0-85% | 0-100% | 30-100% | 0-100% |
| Pattern Hold (bars) | N/A | 8-32 | 8-32 | 16-64 |
| Color Hold (bars) | 64+ | 8-32 | 8-32 | 32-64 |
| Audio Reactivity | OFF | Full | Full | Smoothed |
| Song Detection | Cue-based | Silence gap | Silence gap | Continuous flow |

## Appendix B: Quick Reference -- What Changes Per Genre (Concert)

| Parameter | Rock | EDM | Pop | Hip-Hop | Jazz | Country |
|---|---|---|---|---|---|---|
| Move Speed (Hz) | 0.1-0.6 | 0.2-2.0 | 0.15-0.8 | 0.05-0.3 | 0 | 0.05-0.2 |
| Beat Tightness | Heavy | Tight | Natural | Laid-back | OFF | Musical |
| Attack Delay (ms) | 35 | 5 | 20 | 55 | N/A | 40 |
| Strobe/Song | 2 | 6 | 1 | 1 | 0 | 0 |
| Max Saturation | 1.0 | 1.0 | 0.9 | 0.9 | 0.5 | 0.7 |
| Max Intensity | 100% | 100% | 100% | 80% | 70% | 90% |
| Fade Time (s) | 1.0 | 0.1 | 0.3 | 2.0 | 8.0 | 3.0 |
| Backlight Emphasis | Heavy | Normal | Normal | Moderate | Minimal | Warm |
| Primary Colors | Red/Amber | Cyan/Mag | Pink/Teal | Purple/Gold | Amber/Blue | Amber/White |

## Appendix C: Decision Engine State Behavior Summary

### Per-State Effect Selection (Concert/EDM Default)

| State | Intensity | Movement | Dimmer Effect | Strobe | Color |
|---|---|---|---|---|---|
| INTRO | 30-50% | None or circle_slow | breathing | OFF | Single muted color |
| BUILDUP | 30 to 90% rising | Accelerating sweep/chase | ramp_up | Slow to fast cont. | Shifting toward drop palette |
| PEAK | 100% | Ballyhoo/chase/snap static | beat_kick (4-on-floor) | BURST then beat-locked | Max saturation, 2-3 colors |
| SUSTAIN | 70-90% | Circle/chase/mirror | beat_sync | Occasional beat-locked | Saturated, genre palette |
| BREAKDOWN | 15-40% | None or circle_slow | breathing | OFF | Single cool color |
| OUTRO | Fading | None | ramp_down | OFF | Fading to single color |

---

*This guide is a living document. As the Intelligent Lighting System evolves and is tested in real-world environments, these parameters should be refined based on operator feedback and audience response. The values provided are professional starting points calibrated from two decades of touring, club, festival, and theatrical lighting design experience.*
