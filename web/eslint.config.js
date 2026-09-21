import pluginVue from 'eslint-plugin-vue'
import tseslintParser from '@typescript-eslint/parser'

export default [
  ...pluginVue.configs['flat/recommended'],
  {
    // 纯 TS 文件用 TS 解析器
    files: ['**/*.ts'],
    languageOptions: {
      parser: tseslintParser,
      parserOptions: { sourceType: 'module' },
    },
  },
  {
    // .vue 由 vue-eslint-parser 负责，<script lang="ts"> 交给 TS 解析器
    files: ['**/*.vue'],
    languageOptions: {
      parserOptions: { parser: tseslintParser },
    },
  },
  {
    rules: {
      // 后端已去掉服务端转义，XSS 防线在前端渲染层：禁止 v-html，工具强制
      'vue/no-v-html': 'error',
      'vue/multi-word-component-names': 'off',
      'vue/no-unused-vars': 'warn',
      // 以下为纯格式偏好，与项目紧凑模板写法冲突，关闭以减少噪音
      'vue/max-attributes-per-line': 'off',
      'vue/singleline-html-element-content-newline': 'off',
      'vue/multiline-html-element-content-newline': 'off',
      'vue/html-closing-bracket-newline': 'off',
      'vue/first-attribute-linebreak': 'off',
    },
  },
  {
    ignores: ['dist/**', 'node_modules/**'],
  },
]
