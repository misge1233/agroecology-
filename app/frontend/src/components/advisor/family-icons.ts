import { Beef, Sprout, Trees, Waves, Wheat, type LucideIcon } from "lucide-react";

export const FAMILY_ICONS: Record<string, LucideIcon> = {
  "Crop production and management": Wheat,
  "Livestock production and management": Beef,
  "Integrated soil fertility management": Sprout,
  "Erosion control and water management": Waves,
  "Agro-forestry and forest management": Trees,
};

/** One representative practice photo per challenge family (public/practices). */
export const FAMILY_IMAGES: Record<string, string> = {
  "Crop production and management": "/practices/intercropping.webp",
  "Livestock production and management": "/practices/pasture-management.webp",
  "Integrated soil fertility management": "/practices/isfm.webp",
  "Erosion control and water management": "/practices/water-harvesting.webp",
  "Agro-forestry and forest management": "/practices/multistrata-agroforestry.webp",
};