const fs = require('fs');
const path = require('path');
function walk(dir) {
  fs.readdirSync(dir).forEach(f => {
    let p = path.join(dir, f);
    if (fs.statSync(p).isDirectory()) walk(p);
    else if (p.endsWith('.tsx')) {
      let c = fs.readFileSync(p, 'utf8');
      if (c.includes('import React from "react"')) {
        fs.writeFileSync(p, c.replace(/import React from "react"(\r?\n)?/, ''));
      }
    }
  });
}
walk('src/components');
walk('src/pages');
