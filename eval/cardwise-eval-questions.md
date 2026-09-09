# CardWise RAG — Eval Set (draft, needs verification)

**Status:** verified by Pallav, Sept 9 2026. Questions 8, 16 and 17 were replaced after verification; re-verify those three, then freeze the set.

**Your job before this is usable:** open each predicted file, confirm or correct it, and delete any question whose subject doesn't exist in the codebase. Mark each row DONE when verified.

**Scoring:** recall@5 — a question passes if every file in "Expected" appears in the top 5 retrieved chunks. Cross-platform questions require *all* listed files, which is the point of them.

---

## Locate (10)

| # | Question | Expected (predicted) | Verified |
|---|---|---|---|
| 1 | Where is the logic that picks the best card for a purchase? | `app/src/main/java/com/cardwise/domain/RecommendationEngine.kt` | ☐ |
| 2 | Where is the app's global UI state held on Android? | `app/src/main/java/com/cardwise/ui/AppState.kt` | ☐ |
| 3 | Where are the core domain models defined on iOS? | `ios/CardWiseKit/Sources/CardWiseKit/Domain/Models.swift` | ☐ |
| 4 | Where is the seed/demo data defined? | `app/src/main/java/com/cardwise/domain/SeedData.kt` | ☐ |
| 5 | Which file defines the shared/reusable UI components on Android? | `app/src/main/java/com/cardwise/ui/components/CardWiseComponents.kt` | ☐ |
| 6 | Where is the Supabase project configured? | `supabase/config.toml` | ☐ |
| 7 | Where is the form for adding or editing a card in the admin panel? | `admin/js/card-form.js` | ☐ |
| 8 | Where is the database schema for a user's saved cards first defined? | earliest relevant `supabase/migrations/*.sql` | ☐ |
| 9 | Where is the app's navigation/entry point on Android? | `app/src/main/java/com/cardwise/ui/CardWiseApp.kt` | ☐ |
| 10 | Where is the wallet screen implemented on iOS? | `ios/CardWise/Sources/WalletView.swift` | ☐ |

## Explain (10)

| # | Question | Expected (predicted) | Verified |
|---|---|---|---|
| 11 | How does the recommendation engine rank cards — what inputs does it score on? | `RecommendationEngine.kt` | ☐ |
| 12 | What settings can a user change, and where are they persisted? | `SettingsScreen.kt` + wherever persistence lives | ☐ |
| 13 | What does the home screen show, and where does that data come from? | `HomeScreen.kt`, `AppState.kt` | ☐ |
| 14 | How is a reward category represented in the database schema? | relevant `supabase/migrations/*.sql` | ☐ |
| 15 | What happens when a user adds a card to their wallet? | `WalletScreen.kt` + data layer | ☐ |
| 16 | What does the earliest migration create, and what does the most recent one add? | first and last `supabase/migrations/*.sql` by filename | ☐ |
| 17 | How does the admin panel talk to Supabase, and what does it send? | `admin/js/card-form.js` or a sibling in `admin/` | ☐ |
| 18 | What does the CI pipeline run on a pull request? | `.github/workflows/*.yml` | ☐ |
| 19 | What edge cases does the Android recommendation test suite cover? | `RecommendationEngineTest.kt` | ☐ |
| 20 | How is the iOS project split between `CardWise` and `CardWiseKit`? | `Models.swift`, iOS package manifest, README | ☐ |

## Trace (10)

| # | Question | Expected (predicted) | Verified |
|---|---|---|---|
| 21 | What calls the recommendation engine on Android? | `RecommendationEngine.kt` + its callers in `ui/` | ☐ |
| 22 | Which screens read from `AppState`? | `AppState.kt` + `HomeScreen.kt`, `WalletScreen.kt`, `SettingsScreen.kt` | ☐ |
| 23 | Which tables does the Android app read from? | migrations + Android data layer | ☐ |
| 24 | What writes to the cards table? | `admin/js/card-form.js` + relevant migration | ☐ |
| 25 | Where is `CardWiseComponents` used? | `CardWiseComponents.kt` + the screens importing it | ☐ |

## Cross-platform (5) — the ones that matter

These require chunks from **two or more** platforms in the top 5. If retrieval returns only Kotlin, that's the finding worth writing up.

| # | Question | Expected (predicted) | Verified |
|---|---|---|---|
| 26 | Do the Kotlin and Swift recommendation engines produce the same result for the same input? | `RecommendationEngine.kt` **and** `RecommendationEngineTests.swift` | ☐ |
| 27 | How does the settings screen differ between iOS and Android? | `SettingsScreen.kt` **and** `SettingsView.swift` | ☐ |
| 28 | How does the wallet screen differ between iOS and Android? | `WalletScreen.kt` **and** `WalletView.swift` | ☐ |
| 29 | Which fields of the cards table are used by all three clients? | migration + Android data layer + `Models.swift` + `admin/js/card-form.js` | ☐ |
| 30 | Is the same validation applied on Android, iOS, and the admin panel? | the three validation sites, wherever they are | ☐ |

---

## Notes

- **#16 and #29 are the strongest questions here** — they can only be answered by combining files, which is what retrieval is supposed to be good at and where whole-file chunking may lose to something smarter.
- If a question turns out to have no answer in the code (the feature doesn't exist), delete it rather than softening it. 26 real questions beat 30 padded ones.
- Do not edit this set after you start running evals. Changing the test after seeing the score is how the number becomes meaningless.
