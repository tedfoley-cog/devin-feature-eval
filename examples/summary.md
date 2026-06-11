# Eval summary


## deepwiki-qa

| arm | n | mean ACUs [95% CI] | median ACUs | accuracy [95% CI] | success rate | ACUs/success |
|---|---|---|---|---|---|---|
| no-wiki | 16 | 5.59 [4.30,6.79] | 6.43 | 0.61 [0.53,0.69] | 31% | 17.87806657620213 |
| wiki | 16 | 4.00 [3.47,4.52] | 4.22 | 0.69 [0.61,0.78] | 56% | 7.10957748133088 |
| askdevin-prompt | 16 | 3.83 [3.31,4.35] | 3.89 | 0.86 [0.80,0.92] | 88% | 4.3762030094092434 |

Mann-Whitney U (wiki vs no-wiki, ACUs): p=0.0275

Mann-Whitney U (askdevin-prompt vs no-wiki, ACUs): p=0.0205

## playbook-coding

| arm | n | mean ACUs [95% CI] | median ACUs | accuracy [95% CI] | success rate | ACUs/success |
|---|---|---|---|---|---|---|
| raw-prompt | 16 | 8.85 [7.47,10.20] | 9.84 | 0.62 [0.52,0.71] | 38% | 23.60958306554191 |
| playbook | 16 | 4.77 [4.30,5.25] | 4.66 | 0.78 [0.70,0.86] | 62% | 7.635522294305988 |

Mann-Whitney U (playbook vs raw-prompt, ACUs): p=0.0002
