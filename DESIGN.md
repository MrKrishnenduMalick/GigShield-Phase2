# Design System Strategy: The Radiant Guard

## 1. Overview & Creative North Star: "The Vibrant Architect"
This design system moves away from the cold, sterile aesthetics of traditional finance. Our North Star is **"The Vibrant Architect"**—a philosophy that balances the playful, gamified energy of Duolingo with the sophisticated, technical precision of Stripe. 

We break the "template" look by rejecting rigid, boxed-in layouts. Instead, we use **intentional asymmetry**, organic overlapping of glass elements, and dramatic typographic scales. The goal is a UI that feels alive and breathable, utilizing "white space" not just as a gap, but as a structural element that allows our vibrant gradients and high-energy colors to pop without overwhelming the user.

---

## 2. Colors & Surface Philosophy
The palette is a high-contrast mix of technical stability (`primary`: `#4647D3`) and energetic optimism (`tertiary`: `#844F00` / `#FE9D00`).

### The "No-Line" Rule
**Borders are a design failure.** In this system, 1px solid strokes for sectioning are strictly prohibited. Boundaries must be defined solely through:
*   **Background Shifts:** Place a `surface-container-low` (#EEF1F3) section directly against a `surface` (#F5F7F9) background.
*   **Tonal Transitions:** Use soft shifts in saturation to define content blocks.

### Surface Hierarchy & Nesting
Think of the UI as a physical stack of frosted material.
1.  **Base Layer:** `surface` (#F5F7F9) – The canvas.
2.  **Section Layer:** `surface-container-low` (#EEF1F3) – To group related content modules.
3.  **Interaction Layer:** `surface-container-lowest` (#FFFFFF) – For primary cards and input areas to create a "lifted" appearance.

### The "Glass & Gradient" Rule
To achieve a premium, custom feel, use **Glassmorphism** for floating headers or navigation bars. 
*   **Recipe:** `surface-container-lowest` at 70% opacity + 20px Backdrop Blur.
*   **Signature Textures:** Main CTAs must use a linear gradient from `primary` (#4647D3) to `primary-container` (#9396FF) at a 135° angle. This adds "soul" and depth that flat hex codes cannot replicate.

---

## 3. Typography: The Editorial Voice
We use **Manrope** for its geometric yet approachable character. The hierarchy is designed to feel like a high-end tech editorial.

*   **Display Scale (`display-lg` to `display-sm`):** Reserved for "Hero" moments (e.g., total balance, savings goals). Use tight letter-spacing (-2%) to make it feel authoritative.
*   **Headline & Title:** Use `headline-md` (#2C2F31) for section starts. Ensure generous top-margin to let the heading "own" the space.
*   **Body & Labels:** `body-md` is our workhorse. Use `on-surface-variant` (#595C5E) for secondary metadata to create a clear visual "quietness" against vibrant headlines.

---

## 4. Elevation & Depth
Depth is achieved through **Tonal Layering**, not structural scaffolding.

*   **The Layering Principle:** To highlight a "Gig Income" card, place a `surface-container-lowest` (#FFFFFF) card on top of a `surface-container` (#E5E9EB) background. The contrast provides all the "border" you need.
*   **Ambient Shadows:** For high-priority floating elements (e.g., FABs or Modals), use a diffusion-heavy shadow: `0px 20px 40px rgba(70, 71, 211, 0.08)`. Notice the shadow is tinted with the `primary` color, making it feel integrated with the light source.
*   **The "Ghost Border" Fallback:** If a divider is essential for accessibility, use `outline-variant` (#ABADAF) at **15% opacity**. It should be felt, not seen.

---

## 5. Components

### Buttons & Interaction
*   **Primary:** High-energy gradient (Primary to Primary-Container). `xl` (3rem) corner radius.
*   **Secondary:** `surface-container-highest` background with `on-surface` text. No border.
*   **Tertiary:** Transparent background, `primary` text, bold weight.

### Cards & Lists
*   **Constraint:** Zero dividers. 
*   **Styling:** Use `md` (1.5rem) or `lg` (2rem) corner radius. 
*   **Layout:** Group list items using a shared `surface-container-low` background "pod" rather than individual lines between items.

### Floating Glass Chips
*   Used for status (e.g., "Protected" or "Pending"). 
*   **Style:** Semi-transparent versions of `secondary-container` or `tertiary-container` with a subtle white "Ghost Border."

### Specialized "Gig" Components
*   **Earnings Tracker:** Use a large `display-md` value with a `secondary` (#00647B) to `secondary-fixed-dim` (#37D4FF) gradient.
*   **Shield Status:** A glassmorphic "Shield" icon container using `backdrop-blur` to sit over vibrant background patterns.

---

## 6. Do's and Don'ts

### Do:
*   **Do** use asymmetrical layouts where one element (like a card) slightly overlaps the header or the next section.
*   **Do** lean into the `xl` (3rem) roundedness for large containers to maintain the "Friendly" brand promise.
*   **Do** use `tertiary` (#FE9D00) sparingly as a "High-Energy" accent for alerts or achievement milestones.

### Don't:
*   **Don't** use 100% black text. Always use `on-background` (#2C2F31) to maintain the soft, premium feel.
*   **Don't** use standard "drop shadows" with grey hex codes. They muddy the vibrant palette.
*   **Don't** cram content. If in doubt, increase the vertical spacing by one step on the scale.