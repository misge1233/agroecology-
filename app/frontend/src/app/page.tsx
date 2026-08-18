import { HomeHero } from "@/components/home/hero";
import { HomeStats } from "@/components/home/stats";
import { HomeHow } from "@/components/home/how";
import { HomePowers } from "@/components/home/powers";
import { HomeDemo } from "@/components/home/demo";
import { HomeFamilies } from "@/components/home/families";
import { HomeProvenance } from "@/components/home/provenance";
import { SiteFooter } from "@/components/site-footer";

export default function HomePage() {
  return (
    <>
      <HomeHero />
      <HomeStats />
      <HomeHow />
      <HomePowers />
      <HomeDemo />
      <HomeFamilies />
      <HomeProvenance />
      <SiteFooter />
    </>
  );
}
