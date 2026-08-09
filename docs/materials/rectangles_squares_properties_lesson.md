# Properties of Rectangles and Squares

## Slide 1 — Welcome & Lesson Objectives
Welcome to our lesson on special quadrilaterals! In this lesson, we will explore the geometric properties, definitions, and theorems of rectangles and squares.
- Define rectangles and squares based on their interior angles and side lengths.
- Deduce and prove the key properties of a rectangle's diagonals using triangle congruence.
- Understand the perpendicular and angle-bisecting properties of square diagonals.
- Apply diagonal and side relationships to solve geometric and real-world construction problems.
- Classify special quadrilaterals using mathematical reasoning and Venn diagrams.

## Slide 2 — What is a Rectangle?
- A **rectangle** is a quadrilateral in which all four angles are right angles (each measures $90^\circ$).
- From this definition, we can deduce two important side properties:
  - The opposite sides of a rectangle are of equal length.
  - The opposite sides of a rectangle are parallel to each other.
- Since its opposite sides are parallel, every rectangle is also a parallelogram, inheriting all of its properties.

## Slide 3 — The Diagonals of a Rectangle
- Diagonals are line segments connecting opposite vertices of a quadrilateral, such as $AC$ and $BD$ in a rectangle $ABCD$.
- In any rectangle, the diagonals have two very special properties:
  - **They are equal in length:** The distance from corner $A$ to $C$ is exactly the same as from $B$ to $D$ ($AC = BD$).
  - **They bisect each other:** This means they intersect at their exact midpoints, dividing each other into two equal parts ($OA = OC$ and $OB = OD$).

## Slide 4 — Proving Diagonals are Equal
- We can prove that the diagonals of a rectangle $ABCD$ are equal using **SAS (Side-Angle-Side) triangle congruence**:
  - The opposite sides of a rectangle are equal, so $AB = CD$.
  - The interior angles are right angles: $\angle BAD = \angle CDA = 90^\circ$.
  - The base side $AD$ is shared (common) by both triangles $\triangle ADC$ and $\triangle DAB$.
- Therefore, $\triangle ADC \cong \triangle DAB$ by the SAS congruence condition.
- By corresponding parts of congruent triangles (CPCT), we conclude that diagonal $AC = BD$.

## Slide 5 — Proving Diagonals Bisect Each Other
- We can prove that the diagonals of a rectangle $ABCD$ intersect at their midpoints using **AAS (Angle-Angle-Side) triangle congruence**:
  - The opposite sides of a rectangle are parallel ($AB \parallel CD$), so the alternate interior angles are equal: $\angle 1 = \angle 2$.
  - The vertically opposite angles are equal: $\angle AOB = \angle COD$.
  - The opposite sides are equal: $AB = CD$.
- Therefore, $\triangle AOB \cong \triangle COD$ by the AAS congruence condition.
- By CPCT, we find $OA = OC$ and $OB = OD$, proving the diagonals bisect each other.

## Slide 6 — What is a Square?
- A **square** is a quadrilateral in which all the angles are equal to $90^\circ$, and all four sides are of equal length.
- A square is a special type of rectangle because it meets all the criteria of a rectangle, but has the additional condition of having all four sides equal.
- This means that **every square is a rectangle**, but clearly, not every rectangle is a square.
- A square also meets the definition of a parallelogram and a rhombus.

## Slide 7 — The Diagonals of a Square
- Since a square is a rectangle, its diagonals are equal in length and bisect each other.
- However, square diagonals have an additional property: they are **perpendicular bisectors**.
- This means that they intersect at a right angle ($90^\circ$):
  $$\angle BOA = \angle BOC = \angle COD = \angle DOA = 90^\circ$$
- We prove this using SSS congruence of adjacent triangles $\triangle BOA \cong \triangle BOC$, where the sides $AB = BC$ are equal in a square.

## Slide 8 — Angles and Diagonals of a Square
- The diagonals of a square also **bisect its corner angles**.
- Since each corner angle of a square is $90^\circ$, the diagonal splits it into two equal halves of $45^\circ$ each:
  $$\angle 1 = \angle 2 = \angle 3 = \angle 4 = 45^\circ$$
- In the right-angled isosceles triangle $\triangle ADC$ formed by diagonal $AC$, the base angles must be equal, giving us $\angle 1 = \angle 3 = 45^\circ$.

## Slide 9 — Categorizing Special Quadrilaterals
- We use **Venn diagrams** to represent relationships between different geometric families:
  - The outer set is the family of **parallelograms** (opposite sides are parallel).
  - Inside parallelograms, we have separate sets for **rectangles** (all angles $90^\circ$) and **rhombuses** (all sides equal).
  - The intersection where rectangles and rhombuses overlap contains **squares** because a square has both $90^\circ$ angles and equal sides.

## Slide 10 — Worked Examples: Rectangle Diagonals
- **Example 1:** In a rectangle $ABCD$, the diagonals intersect at point $O$. If $OA = 5\text{ cm}$, find the length of the diagonal $BD$.
  - *Solution:* Since the diagonals of a rectangle bisect each other, the point $O$ is the midpoint of diagonal $AC$.
  - Therefore, the full diagonal $AC = 2 \times OA = 2 \times 5\text{ cm} = 10\text{ cm}$.
  - Since the diagonals of a rectangle are equal in length, $BD = AC = 10\text{ cm}$.
- **Example 2:** A carpenter places two wooden strips of equal length such that they bisect each other at their midpoints. What shape is formed when a thread is passed through their endpoints?
  - *Solution:* When two line segments of equal length bisect each other, they represent equal diagonals that bisect each other. This is the exact geometric condition for a **rectangle**.

## Slide 11 — Worked Examples: Geometric Logic
- **Example 3:** If square $CASE$ has side length $2x$, and $U, V, W, X$ are the midpoints of its sides, prove that $UVWX$ is also a square.
  - *Solution:* The midpoints split each side of length $2x$ into segments of length $x$.
  - In each corner, we have a right-angled isosceles triangle (such as $\triangle CUV$ with $\angle C = 90^\circ$ and $CU = CV = x$).
  - By the Pythagorean theorem, the hypotenuse $UV = \sqrt{x^2 + x^2} = x\sqrt{2}$. All four sides of $UVWX$ are of equal length $x\sqrt{2}$.
  - Since the base angles of each corner triangle are $45^\circ$, each interior angle of $UVWX$ is $180^\circ - 45^\circ - 45^\circ = 90^\circ$ (by linear pair).
  - Thus, $UVWX$ has four equal sides and four $90^\circ$ angles, making it a **square**.

## Slide 12 — Common Mistakes to Avoid
- **Mistake 1: Believing any quadrilateral with equal diagonals is a rectangle.**
  - *Incorrect:* "If $AC = BD$, then $ABCD$ must be a rectangle."
  - *Correct:* The diagonals must also **bisect each other**. An isosceles trapezium also has equal diagonals, but it is not a rectangle because they do not bisect each other.
- **Mistake 2: Assuming diagonals of all parallelograms are equal.**
  - *Incorrect:* "Since opposite sides are equal, the diagonals must be equal."
  - *Correct:* Diagonals of a parallelogram are only equal if the angles are $90^\circ$ (making it a rectangle).
- **Mistake 3: Thinking any quadrilateral with perpendicular diagonals is a square.**
  - *Incorrect:* "Since the diagonals intersect at $90^\circ$, it is a square."
  - *Correct:* Kites and rhombuses also have perpendicular diagonals, but they do not have four equal angles of $90^\circ$.

## Slide 13 — Lesson Summary
- **Rectangle Definition:** Quadrilateral with all angles equal to $90^\circ$. Opposite sides are equal and parallel.
- **Rectangle Diagonals:** Diagonals are of equal length ($AC = BD$) and bisect each other ($OA = OC$, $OB = OD$).
- **Square Definition:** Quadrilateral with all angles equal to $90^\circ$ and all sides of equal length.
- **Square Diagonals:** Equal in length, bisect each other at $90^\circ$, and bisect the corner angles into $45^\circ$ halves.
- **Venn Diagram Class:** A square is a rectangle, a rhombus, and a parallelogram.
