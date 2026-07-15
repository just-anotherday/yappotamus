export const panmeeRecipe = {
  id: 'panmee',
  title: 'HOW TO MAKE PAN MEE',
  author: 'JASON YAP',
  cookTime: 'COOK TIME 2 HOURS',
  baseServings: 2,
  heroImages: [
    {
      src: '/assets/panmee_photo/image002.jpg',
      alt: 'Pan Mee - Finished dish showing noodles in anchovy broth with toppings',
    },
  ],
  intro:
    'Greetings everyone! This recipe provides detailed steps to making Pan Mee, a Malaysian Chinese dish with anchovy-rich broth, hand-torn noodles made from scratch, and savory pork + shiitake topping.',
  preparation: {
    paragraphs: [
      'Neck pork bones are my soup bone of choice, but any meat bones would do. Chicken bones are another popular choice.',
      'Generally, you want to mince your topping ingredients so they are subtle in your dish. Dice Thai chili peppers and set them aside for more exciting taste.',
    ],
    images: [
      { src: '/assets/panmee_photo/image006.jpg', alt: 'Pork bones and soup ingredients prepared' },
      { src: '/assets/panmee_photo/image008.jpg', alt: 'Minced garlic, ginger and shallots' },
      { src: '/assets/panmee_photo/image010.jpg', alt: 'Soaked shiitake mushrooms' },
      { src: '/assets/panmee_photo/image012.jpg', alt: 'Diced Thai chili peppers' },
    ],
  },
  ingredients: [
    {
      title: 'DELICIOUS INGREDIENTS',
      items: [
        { amount: 1, unit: 'bunch', label: 'Yu Choy, cleaned and prewashed' },
        { label: 'Vegetable oil, for frying' },
        { amount: 100, unit: 'grams (g)', label: 'dried anchovy, heads removed' },
      ],
    },
    {
      title: 'ANCHOVY SOUP BASE',
      items: [
        { amount: 4, unit: 'cups', label: 'water' },
        { amount: 1, unit: 'lbs', label: 'pork bones' },
        { amount: 0.25, unit: 'lb', label: 'dried anchovy' },
        { amount: 0.5, unit: 'large', label: 'yellow onion, halved' },
        { amount: 1, unit: 'tsp', label: 'fish sauce, to taste' },
        { amount: 0.5, unit: 'tsp', label: 'white peppercorn, crushed' },
        { amount: 0.5, unit: 'thumb-size', label: 'ginger, quartered' },
        { amount: 1, unit: '', label: 'honey date' },
      ],
    },
    {
      title: 'NOODLES / DOUGH',
      items: [
        { amount: 2, unit: 'cups', label: 'all-purpose flour' },
        { amount: 1, unit: 'tbsp', label: 'vegetable oil' },
        { amount: 1, unit: 'cup', label: 'water (start with 3/4 cup, add more as needed)' },
        { amount: 0.5, unit: 'tsp', label: 'salt' },
        { amount: 0.5, unit: 'tsp', label: 'sugar' },
        { amount: 0.5, unit: 'tbsp', label: 'cornstarch' },
      ],
    },
    {
      title: 'GROUND PORK & SHIITAKE TOPPING',
      items: [
        { amount: 0.5, unit: 'lb', label: 'ground pork' },
        { amount: 6, unit: 'pieces', label: 'dried shiitake mushroom, soaked' },
        { amount: 3, unit: 'cloves', label: 'garlic, minced' },
        { amount: 1, unit: '', label: 'shallot, minced' },
        { amount: 0.5, unit: 'thumb-size', label: 'ginger, minced' },
        { amount: 0.5, unit: 'tsp', label: 'chicken bouillon powder' },
        { amount: 1, unit: 'tbsp', label: 'fish sauce' },
      ],
    },
    {
      title: 'DIPPING SAUCE (SPICY)',
      items: [
        { amount: 6, unit: '', label: 'Thai chili peppers, chopped' },
        { label: 'Soy sauce, to taste' },
      ],
    },
  ],
  instructions: [
    {
      title: 'STEP 1: Preparing the Soup Base',
      text:
        'Rinse pork bones under cold water while removing impurities. Repeat until water is clear for a cleaner broth.',
      images: [
        { src: '/assets/panmee_photo/image014.jpg', alt: 'Rinsing pork bones in clear water' },
        { src: '/assets/panmee_photo/image016.jpg', alt: 'Cleaned pork bones ready for soup' },
      ],
    },
    {
      title: 'STEP 2: Cooking the Soup',
      text:
        'Bring water to boil, add soup ingredients, reduce to low, and simmer with lid on for around 2 hours. Adjust seasoning to taste.',
      images: [
        { src: '/assets/panmee_photo/image018.jpg', alt: 'Soup ingredients in boiling water' },
        { src: '/assets/panmee_photo/image020.jpg', alt: 'Simmering soup with lid closed' },
        { src: '/assets/panmee_photo/image022.jpg', alt: 'Close-up of soup ingredients' },
      ],
    },
    {
      title: 'STEP 3: Preparing the Dough',
      text:
        'Mix flour, water, oil, salt, sugar, and cornstarch. Knead until smooth and non-sticky, then rest at least one hour.',
      images: [
        { src: '/assets/panmee_photo/image024.jpg', alt: 'Mixing dough ingredients' },
        { src: '/assets/panmee_photo/image026.jpg', alt: 'Kneading the dough' },
        { src: '/assets/panmee_photo/image028.jpg', alt: 'Dough ingredients close-up' },
        { src: '/assets/panmee_photo/image030.jpg', alt: 'Resting dough covered' },
      ],
    },
    {
      title: 'STEP 4: Preparing the Pork & Mushroom Topping',
      text:
        'Stir fry ground pork until dry, add aromatics, then mushrooms, bouillon, and fish sauce. Simmer to preferred consistency.',
      images: [
        { src: '/assets/panmee_photo/image032.jpg', alt: 'Stir-frying ground pork' },
        { src: '/assets/panmee_photo/image034.jpg', alt: 'Adding mushrooms to pork' },
      ],
    },
    {
      title: 'STEP 5: Frying Anchovies',
      text:
        'Fry dried anchovies in 350°F oil for 10-15 minutes until golden and crisp. Strain and cool on napkin-lined plate.',
      images: [
        { src: '/assets/panmee_photo/image036.jpg', alt: 'Frying dried anchovies in oil' },
        { src: '/assets/panmee_photo/image038.jpg', alt: 'Crispy fried anchovies' },
      ],
    },
    {
      title: 'STEP 6: Preparing the Noodles',
      text:
        'Bring salted water with a little oil to boil, stretch and tear dough into noodle pieces, then drop into boiling water.',
      images: [
        { src: '/assets/panmee_photo/image040.jpg', alt: 'Tearing dough into noodles' },
        { src: '/assets/panmee_photo/image042.jpg', alt: 'Hand-torn noodle pieces' },
        { src: '/assets/panmee_photo/image044.jpg', alt: 'Noodles cooking in boiling water' },
      ],
    },
    {
      title: 'STEP 7: Cooking Noodles and Vegetables',
      text:
        'Once noodles float, strain into bowls. Use same water to boil leafy greens for 3-5 minutes to desired tenderness.',
      images: [
        { src: '/assets/panmee_photo/image046.jpg', alt: 'Straining cooked noodles' },
        { src: '/assets/panmee_photo/image048.jpg', alt: 'Boiling Yu Choy vegetables' },
      ],
    },
  ],
  assembly: [
    {
      title: 'STEP 1: Final Preparation',
      text: 'Heat soup to rolling boil and skim impurities on top for a cleaner presentation.',
      images: [],
    },
    {
      title: 'STEP 2: Plating',
      text: 'Place noodles in bowl, add topping and vegetables, and garnish to preference.',
      images: [
        { src: '/assets/panmee_photo/image050.jpg', alt: 'Plating noodles in bowl' },
        { src: '/assets/panmee_photo/image052.jpg', alt: 'Adding toppings to noodles' },
      ],
    },
    {
      title: 'STEP 3: Serving',
      text: 'Pour hot soup over everything, top with crispy anchovies, and serve immediately.',
      images: [
        { src: '/assets/panmee_photo/image054.jpg', alt: 'Finished Pan Mee dish ready to serve' },
      ],
    },
  ],
  notes: [
    'Break chilis smaller for extra heat.',
    'Use plain soy sauce if you prefer non-spicy dipping sauce.',
    'Recipe quantities adjust automatically with serving controls.',
  ],
}
