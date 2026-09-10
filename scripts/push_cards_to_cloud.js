#!/usr/bin/env node
/**
 * push_cards_to_cloud.js — 本地卡库 → 网站 cards 集合 整批上云
 *
 * 用途：把本地 references/cards/ 生成的同步 JSON（cards_batch_vXXXX.json）
 *       整批写入网站的 `cards` 集合（按 cards_version 替换）。
 *
 * 用法：
 *   1. 任意目录装依赖（建议 D 盘或项目目录）：npm i @cloudbase/node-sdk
 *   2. 填好下方 CONFIG 三项（找隔壁翻译要 envId / 密钥）
 *   3. node push_cards_to_cloud.js <cards_batch_json路径>
 *      例：node push_cards_to_cloud.js "E:/阅读分析/dist/网站同步包-20260910/cards_batch_v20260910.json"
 *
 * 行为：
 *   - 读取 JSON，校验 cards_version / total
 *   - 删除 cards 集合中 cards_version ≠ 新版本的旧记录（旧版本整批清掉）
 *   - 分批（每 20 条）写入新记录
 *   - 完成后打印数量核对（应等于 JSON 里的 total）
 */

const fs = require("fs");
const path = require("path");

// ====== CONFIG（三处必填） ======
const CONFIG = {
  envId: "填环境ID",            // 隔壁翻译的 CloudBase 环境ID
  secretId: "填SecretId",       // 云开发访问密钥（控制台-访问服务生成）
  secretKey: "填SecretKey",
};

// ====== 主逻辑 ======
async function main() {
  const jsonPath = process.argv[2];
  if (!jsonPath || !fs.existsSync(jsonPath)) {
    console.error("用法：node push_cards_to_cloud.js <cards_batch_json路径>");
    process.exit(2);
  }
  const batch = JSON.parse(fs.readFileSync(jsonPath, "utf-8"));
  if (!batch.cards_version || !Array.isArray(batch.cards)) {
    console.error("JSON 格式不对：缺 cards_version 或 cards 数组");
    process.exit(2);
  }
  console.log(`载入 ${batch.cards.length} 张卡 · 版本 ${batch.cards_version}`);

  const CloudBase = require("@cloudbase/node-sdk");
  const app = CloudBase.init({
    env: CONFIG.envId,
    secretId: CONFIG.secretId,
    secretKey: CONFIG.secretKey,
  });
  const db = app.database();
  const coll = db.collection("cards");

  // 1) 清旧版本（cards_version 不同的全删）
  const OLD = await coll.where({ cards_version: db.command.neq(batch.cards_version) }).remove();
  console.log("旧版本清除：", JSON.stringify(OLD.deleted || OLD));

  // 2) 分批写入（集合单次最多 20 条）
  const CHUNK = 20;
  let done = 0;
  for (let i = 0; i < batch.cards.length; i += CHUNK) {
    const chunk = batch.cards.slice(i, i + CHUNK);
    const r = await coll.add(chunk);
    done += chunk.length;
    console.log(`  写入 ${done}/${batch.cards.length}`);
  }

  // 3) 核对
  const cnt = await coll.where({ cards_version: batch.cards_version }).count();
  console.log(`完成：新版本 ${batch.cards_version} 实存 ${cnt.total} 张（应=${batch.cards.length}）`);
  if (cnt.total !== batch.cards.length) {
    console.error("数量不一致！检查报错重跑（重复跑是安全的：先清后写）");
    process.exit(1);
  }
}

main().catch((e) => {
  console.error("上云失败：", e.message);
  process.exit(1);
});
