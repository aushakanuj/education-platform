# Square Numbers and Odd Number Sums

## Slide 1 — Welcome & Lesson Objectives
Welcome to Grade 8 Mathematics! In this lesson, we will uncover the hidden patterns within square numbers and discover how they relate to the sum of consecutive odd numbers.
- Define square numbers and identify perfect squares of natural numbers.
- Explore units digit rules to determine when a number is definitely not a perfect square.
- Understand the relationship between ending zeros of a number and its square.
- Apply the Odd Sum Rule to find the square of a number using consecutive odd numbers.
- Use successive subtraction of consecutive odd numbers to verify perfect squares.
- Find and estimate square roots using prime factorization and range intervals.

## Slide 2 — What is a Square Number?
- A **square number** is a number that can be expressed as the product of a number with itself.
- For any number $n$, we write $n \times n = n^2$, which is read as **"$n$ squared"**.
- Geometrically, a square number represents the area of a square. For example, a square with side length 4 units contains $4 \times 4 = 4^2 = 16$ unit squares.
- The squares of natural numbers are called **perfect squares** (such as 1, 4, 9, 16, 25, 36, 49, 64, 81, 100).

## Slide 3 — Units Digit Patterns of Perfect Squares
- Perfect squares of integers can only end with the digits **0, 1, 4, 5, 6, or 9** in their units place.
- No perfect square can ever end with the digits **2, 3, 7, or 8**.
- If a number ends with 2, 3, 7, or 8, we can definitely conclude that it is **not** a perfect square.
- However, if a number ends with 0, 1, 4, 5, 6, or 9, it is *not guaranteed* to be a perfect square (for example, 26 ends in 6 but is not a perfect square, since $5^2 = 25$ and $6^2 = 36$).

## Slide 4 — Parity and Zero Patterns
- **Parity Rule:** The square of an even number is always **even** (for example, $12^2 = 144$), and the square of an odd number is always **odd** (for example, $15^2 = 225$).
- **Zeros Rule:** Perfect squares can only have an **even number of zeros** at the end.
- If a number contains $k$ zeros at the end, its square will contain $2k$ zeros at the end.
- For example, 10 (one zero) squared is 100 (two zeros), and 3000 (three zeros) squared is $9,000,000$ (six zeros). A number ending in exactly 3 zeros can never be a perfect square.

## Slide 5 — Perfect Squares and Odd Numbers
- Adding consecutive odd numbers starting from 1 always yields consecutive square numbers.
- The sum of the first $n$ odd natural numbers is equal to $n^2$:
  $$1 = 1 = 1^2$$
  $$1 + 3 = 4 = 2^2$$
  $$1 + 3 + 5 = 9 = 3^2$$
  $$1 + 3 + 5 + 7 = 16 = 4^2$$
  $$1 + 3 + 5 + 7 + 9 = 25 = 5^2$$
- We can find $n^2$ by summing successive odd numbers starting from 1 up to the $n$-th odd number, which is given by the formula $2n - 1$.

## Slide 6 — Triangular Numbers and Squares
- A **triangular number** is a number that can be represented as a triangular pattern of dots (such as 1, 3, 6, 10, 15).
- If we add two consecutive triangular numbers, we always get a perfect square:
  $$1 + 3 = 4 = 2^2$$
  $$3 + 6 = 9 = 3^2$$
  $$6 + 10 = 16 = 4^2$$
  $$10 + 15 = 25 = 5^2$$
- This beautiful pattern connects triangular geometry directly to square geometry.

## Slide 7 — Finding Square Roots: Successive Subtraction
- The **square root** of a number $y$ is a number $x$ such that $x^2 = y$. It is represented by the symbol $\sqrt{y}$.
- We can find the positive square root of a perfect square by repeatedly subtracting consecutive odd numbers starting from 1 until we reach 0.
- The number of subtraction steps is the square root. Let's find $\sqrt{25}$:
  - Step 1: $25 - 1 = 24$
  - Step 2: $24 - 3 = 21$
  - Step 3: $21 - 5 = 16$
  - Step 4: $16 - 7 = 9$
  - Step 5: $9 - 9 = 0$
  - Since it took 5 steps, $\sqrt{25} = 5$.

## Slide 8 — Finding Square Roots: Prime Factorization
- A number is a perfect square if its prime factors can be split into two identical groups.
- To find the square root of 324:
  1. Write the prime factorization: $324 = 2 \times 2 \times 3 \times 3 \times 3 \times 3$.
  2. Group into pairs of identical factors: $324 = (2 \times 2) \times (3 \times 3) \times (3 \times 3)$.
  3. Pick one factor from each pair and multiply: $2 \times 3 \times 3 = 18$.
- Therefore, $\sqrt{324} = 18$.

## Slide 9 — Estimating Square Roots of Large Numbers
- We can estimate the square root of a non-square or large number by trapping it between two known perfect squares.
- Let's estimate $\sqrt{250}$:
  - We know $15^2 = 225$ and $16^2 = 256$.
  - Since $225 < 250 < 256$, we have $15 < \sqrt{250} < 16$.
  - Because 250 is much closer to 256 than to 225, $\sqrt{250}$ is approximately 16 (but slightly less than 16).

## Slide 10 — Worked Examples: Odd Number Patterns
- **Example 1:** Find $36^2$ given that $35^2 = 1225$.
  - *Solution:* Since $35^2 = 1225$ is the sum of the first 35 consecutive odd numbers, $36^2$ requires adding the 36th odd number.
  - The $n$-th odd number is given by $2n - 1$.
  - For $n = 36$, the 36th odd number is $2(36) - 1 = 71$.
  - Therefore, $36^2 = 1225 + 71 = 1296$.
- **Example 2:** Determine if 576 is a perfect square using estimation.
  - *Solution:* $20^2 = 400$ and $30^2 = 900$, so $20 < \sqrt{576} < 30$.
  - Since 576 ends in 6, its root must end in 4 or 6. Thus, candidates are 24 or 26.
  - Let's check $25^2 = 625$. Since $576 < 625$, the root must be 24.
  - Verify: $24 \times 24 = 576$. Yes, $\sqrt{576} = 24$.

## Slide 11 — Common Mistakes to Avoid
- **Mistake 1: Confusing $n^2$ with $2n$.**
  - *Incorrect:* $6^2 = 6 \times 2 = 12$.
  - *Correct:* $6^2 = 6 \times 6 = 36$.
- **Mistake 2: Assuming any number ending in 0, 1, 4, 5, 6, 9 is a perfect square.**
  - *Incorrect:* "Since 156 ends in 6, it is a perfect square."
  - *Correct:* The units digit can only rule out numbers. $12^2 = 144$ and $13^2 = 169$, so 156 is not a perfect square.
- **Mistake 3: Forgetting the zeros rule.**
  - *Incorrect:* "The square of a number ending in 2 zeros can end in 3 zeros."
  - *Correct:* The number of ending zeros in a square is always even and double the original number of zeros.

## Slide 12 — Lesson Summary
- **Square definition:** $n^2 = n \times n$. Represents the area of a square of side $n$.
- **Units digit:** Perfect squares can only end in 0, 1, 4, 5, 6, or 9. They never end in 2, 3, 7, or 8.
- **Zeros and Parity:** Even squares are even; odd squares are odd. Zeros at the end of a perfect square must be an even number.
- **Odd Sum Rule:** Sum of first $n$ odd numbers is $n^2$. The $n$-th odd number is $2n - 1$.
- **Square Roots:** Solved by successive subtraction, prime factorization, or range estimation.
