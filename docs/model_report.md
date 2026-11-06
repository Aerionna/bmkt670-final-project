# Model Report: Montana Border Crossings

## Training Data Exploration

These charts and statistics use only the 59 training rows (April 2017 through
December 2023, with March 2020 through December 2021 excluded). The validation
and test rows were not examined. The correlations below describe association
only; they do not establish that any feature causes crossing levels.

| Statistic | statewide_crossings (train) |
| :-------- | --------------------------: |
| Count | 59 |
| Mean | 84,551 |
| Standard deviation | 44,943 |
| Minimum | 19,633 |
| Median | 69,347 |
| Maximum | 195,972 |

| Feature | Correlation with statewide_crossings (train) |
| :------ | -------------------------------------------: |
| crossings_rolling_3 | 0.419 |
| usd_cad_rate_lag1 | 0.018 |
| national_travel_lag1 | 0.607 |

### Distribution of the target

![Distribution of monthly statewide crossings, training data](figures/statewide_crossings_distribution.png)

Most training months fall between about 40,000 and 110,000 crossings, but the distribution contains a wide range with a long right tail, where the six highest months (each July and August from 2017 to 2019, at about 185,000–196,000) appear to be seasonal summer peaks.

### Average crossings by season

![Average monthly statewide crossings by season, training data](figures/crossings_by_season.png)

Summer training months average about 145,000 statewide crossings, roughly 2.6 times the winter average of about 54,800 and well above spring (about 60,900) and fall (about 75,900), which suggests a strong seasonal pattern in Montana crossings.

### Target vs. previous month's exchange rate

![Statewide crossings vs. previous month's USD/CAD rate](figures/crossings_vs_exchange_rate.png)

Within the narrow range observed in the training data (about 1.23 to 1.37), the previous month’s USD/CAD rate shows little visible relationship with statewide crossings (r = 0.02), although this does not prove that exchange rates cannot affect travel.

### Target vs. previous month's national automobile travel

![Statewide crossings vs. previous month's Canadian automobile trips](figures/crossings_vs_national_travel.png)

The previous month’s Canadian automobile trips show the strongest visible numerical relationship with statewide crossings (r = 0.61), but national and Montana travel may both reflect the same seasonal pattern, so this association does not show that national travel drives Montana crossings.

## Evaluation Metric

Models were evaluated using mean absolute error (MAE), which measures the average size of the difference between predicted and actual monthly crossings. Random Forest had a validation MAE of 10,096 and a final test MAE of 15,508. In business terms, across the 20 unseen test months, the model’s predictions differed from actual statewide passenger crossings by about 15,500 passengers per month on average. 

## Baseline Model

The baseline predicts the training mean, 84,551 crossings, for every month, using no features. Scored on the 12 validation months (2024), it has an MAE of 33,381 crossings. A later model improves on the baseline only if its validation MAE is lower than 33,381.

## Model Comparison

Three models were trained on the 59 training months using seven features (previous month's exchange rate, national automobile travel and Montana crossings, the three-month rolling average, and three season indicators). Tree depth and leaf size were limited to reduce overfitting on the small training set.

| Model | Validation MAE |
| :---- | -------------: |
| Baseline (training mean) | 33,381 |
| Linear Regression | 19,573 |
| Decision Tree | 13,082 |
| Random Forest | 10,096 |

All three models beat the baseline. Random Forest had the lowest validation MAE, about 70% below the baseline, meaning its 2024 predictions were off by about 10,100 crossings per month on average. These results come from only 12 validation months; the test set has not been used.

## Final Test Result

Random Forest was selected because it had the lowest validation MAE. The same fitted model (trained on the 59 training months only) was then scored once on the 20 test months, January 2025 through August 2026.

| Selected model | Validation MAE (2024) | Test MAE (Jan 2025–Aug 2026) |
| :------------- | --------------------: | ---------------------------: |
| Random Forest | 10,096 | 15,508 |

Test performance was worse: the test MAE was 5,412 crossings (about 53.6%) higher than the validation MAE. The two largest test errors were in August. In August 2026 the model predicted 176,196 crossings against an actual 117,663, an error of −58,533, meaning it predicted too high; August 2025 was overpredicted by a similar amount (−58,642). The model appears to rely heavily on the higher summer levels seen in the pre-COVID training years, when August crossings were about 185,000–192,000. This describes a limitation of the model and does not prove why recent August traffic was lower. More broadly, the higher test MAE may reflect changes in Canadian travel patterns during 2025–2026 that were not fully represented in the training data, and with only 20 test months, a few unusual months can noticeably affect MAE; these explanations were not tested. The August 2026 crossings come from BTS, and the row's travel feature uses July 2026, which is final. The preliminary August 2026 Statistics Canada value matters for a different reason: the ML table only includes months that all three sources share, so that value, which may be revised, is why the August 2026 row exists at all. No model, feature or setting changes were made after viewing the test results.

## Feature Importance

| Feature | Importance |
| :------ | ---------: |
| is_summer | 50.0% |
| crossings_lag1 | 32.0% |
| national_travel_lag1 | 8.8% |
| crossings_rolling_3 | 6.4% |
| is_fall | 1.9% |

The model relied most on whether the month was in summer (50.0%), which matches the training-data finding that summer months averaged about 2.6 times as many crossings as winter months. The previous month's Montana crossings were the second most important signal (32.0%), suggesting the model used recent traffic to gauge the current level of travel. The previous month's Canadian automobile trips were a smaller but useful signal (8.8%); in the training data, higher national travel was associated with higher Montana crossings (r = 0.61). The previous month's exchange rate contributed less than 1%, consistent with its weak relationship with crossings in the training data. Feature importance shows what the model relied on, not what caused changes in crossings, and similar features such as last month's crossings and the three-month average may share importance between them.

## Limitations

The model was trained on only 59 months, including just 24 post-COVID months, so it may not adapt quickly to lasting changes in travel patterns; the recent August overpredictions demonstrate this limitation. BTS counts all inbound personal-vehicle passengers at Montana ports, not specifically Canadian residents or tourists, so the results should be interpreted as border-crossing volume rather than Canadian visitation. The current workflow evaluates historical months with known outcomes and does not yet generate a true forecast for a future month without an actual target row. More post-COVID history—especially additional summer months—and Montana-specific data about traveler residency and trip purpose would help most. Information about border policies, holidays, fuel prices and major events could also improve future models, while preliminary Statistics Canada values may be revised.
