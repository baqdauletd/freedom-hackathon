import { parseCsv, fetchText } from "./client";
import type { BusinessUnit } from "./types";

export const loadBusinessUnits = async (path = "/business_units.csv"): Promise<BusinessUnit[]> => {
  const text = await fetchText(path);

  return parseCsv(text, (row) => ({
    office: row["Офис"],
    address: row["Адрес"],
  }));
};
